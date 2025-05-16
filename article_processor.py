import boto3
import json
import logging
import asyncio
from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, CLAUDE_MODEL_ID, VALID_CATEGORIES

logger = logging.getLogger(__name__)

class ArticleProcessor:
    def __init__(self):
        self.bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        # Configure logging for debugging
        logger.setLevel(logging.DEBUG)
        # Add console handler if not already present
        if not logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        logger.info("Initialized ArticleProcessor with Claude via AWS Bedrock")

    async def classify_article(self, article):
        """Classify article using Claude"""
        system_prompt = """You are an expert in analyzing Spanish news articles from Mexico. Your task is to categorize news articles.

        You MUST only respond with one of these exact words:
        - crime: for crime-related news
        - infrastructure: for infrastructure-related news
        - hazard: for weather alerts, fires, natural disasters
        - social: for political unrest, protests, social events
        - DISCARD: if the article doesn't fit any category

        IMPORTANT: You must ONLY return one of these exact words: crime, infrastructure, hazard, social, or DISCARD.
        No explanation, no additional text, no Spanish translations. Only one word from the specified list."""

        user_message = f"""
        Analiza y clasifica el siguiente artículo de noticias en español:

        Título: {article['title']}
        Contenido: {article['description']}

        Responde SOLAMENTE con una de estas palabras exactas:
        - crime (para delitos, crímenes, inseguridad)
        - infrastructure (para infraestructura, construcciones)
        - hazard (para alertas meteorológicas, incendios, desastres naturales)
        - social (para disturbios políticos, protestas, eventos sociales)
        - DISCARD (si no encaja en ninguna categoría)
        """

        try:
            category = await self._invoke_claude_messages(system_prompt, user_message)
            category = category.strip().lower()

            # Log the exact response for debugging
            logger.debug(f"Raw classification response: '{category}'")

            # Clean up the response (remove quotes, punctuation, whitespace)
            category = category.strip().lower().replace('"', '').replace("'", "").strip('.')

            if category not in VALID_CATEGORIES:
                logger.info(f"Article discarded - invalid category: '{category}'")
                return None

            article['type'] = category
            return article
        except Exception as e:
            logger.error(f"Error classifying article: {e}")
            return None

    async def extract_location(self, article):
        """Extract specific location from article using Claude"""
        system_prompt = """You are an expert in analyzing Spanish news articles from Mexico. Your task is to extract the most specific location mentioned.

        Return ONLY the location name with NO explanation or additional text.
        """

        user_message = f"""
        Extrae la ubicación más específica mencionada en este artículo, puedes deducirlo si no trae explicitamente:

        Título: {article['title']}
        Contenido: {article['description']}

        Responde SOLAMENTE con el nombre de la ubicación, en cuanto más exacto mejor.

        Ejemplo:

        Calle Zamora, Colonia Condesa, Ciudad de Mexico

        Si es internacional o no hay ubicación mexicana clara, responde exactamente con "NO_LOCATION".

        Debes evitar a toda costa poner "NO_LOCATION", solamente en expeciones que la noticia sea de otro pais que no es Mexico o en raros casos que la notiica no tenga ubicacion.
        """

        try:
            location = await self._invoke_claude_messages(system_prompt, user_message)
            location = location.strip()
            logger.debug(f"Raw location response: '{location}'")

            if location.lower() == "no_location" or not location:
                logger.info(f"Article discarded - no location extracted: {article['title']}")
                return None

            # Add Mexico if not already present and not NO_LOCATION
            if not "mexico" in location.lower() and not "méxico" in location.lower():
                location += ", Mexico"

            article['location'] = location
            return article
        except Exception as e:
            logger.error(f"Error extracting location: {e}")
            # Don't discard the article if location extraction fails
            article['location'] = "Mexico"  # Default to country level
            return article

    async def _invoke_claude_messages(self, system_prompt, user_message):
        """Invoke Claude model via AWS Bedrock Messages API"""
        loop = asyncio.get_event_loop()

        def _call_bedrock_messages():
            try:
                logger.debug(f"Sending request to Claude with system prompt: {system_prompt[:50]}...")
                logger.debug(f"User message: {user_message[:50]}...")

                request = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": user_message
                                }
                            ]
                        }
                    ],
                    "max_tokens": 20,
                    "temperature": 0.5,
                    "top_p": 1.0
                }

                # Try with the non-streaming API first
                response = self.bedrock_runtime.invoke_model(
                    modelId=CLAUDE_MODEL_ID,
                    body=json.dumps(request)
                )

                response_body = json.loads(response['body'].read())
                if 'content' in response_body and response_body['content']:
                    content_items = response_body['content']
                    full_response = ""
                    for item in content_items:
                        if item['type'] == 'text':
                            full_response += item['text']

                    logger.debug(f"Full response from Claude: '{full_response}'")
                    return full_response.strip()
                else:
                    logger.error("Response from Claude doesn't contain expected content structure")
                    return ""

            except Exception as e:
                logger.error(f"Error calling Bedrock: {e}")
                # Fallback to a default category to avoid discarding all articles
                return "social"  # Default fallback category

        return await loop.run_in_executor(None, _call_bedrock_messages)

    async def process_articles(self, article_queue, geocoder, db):
        """Process articles from the queue"""
        while True:
            article = await article_queue.get()
            try:
                # Step 1: Classify the article
                classified_article = await self.classify_article(article)
                if not classified_article:
                    article_queue.task_done()
                    continue

                # Step 2: Extract location
                article_with_location = await self.extract_location(classified_article)
                if not article_with_location:
                    article_queue.task_done()
                    continue

                # Step 3: Geocode the location
                geocoded_article = await geocoder.geocode_location(article_with_location)
                if not geocoded_article:
                    article_queue.task_done()
                    continue

                # Step 4: Store in database
                db.insert_article(geocoded_article)
                logger.info(f"Successfully processed article: {article['title']}")
            except Exception as e:
                logger.error(f"Error processing article: {e}")
            finally:
                article_queue.task_done()

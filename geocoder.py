import aiohttp
import asyncio
import logging
from urllib.parse import quote
from config import MAPBOX_ACCESS_TOKEN, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)

class Geocoder:
    def __init__(self):
        self.access_token = MAPBOX_ACCESS_TOKEN
        self.session = None

    async def initialize(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def geocode_location(self, article):
        if not self.session:
            await self.initialize()

        location = article['location']

        for attempt in range(MAX_RETRIES):
            try:
                encoded_location = quote(location)
                url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{encoded_location}.json?access_token={self.access_token}&country=mx&limit=1"

                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        features = data.get('features', [])

                        if features:
                            coordinates = features[0]['center']
                            article['coordinates'] = coordinates
                            return article
                        else:
                            logger.warning(f"No geocoding results for location: {location}")
                            return None
                    else:
                        logger.warning(f"Mapbox API error: {response.status}")
            except Exception as e:
                logger.error(f"Error geocoding location {location}: {e}")

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)

        logger.error(f"Failed to geocode location after {MAX_RETRIES} attempts: {location}")
        return None

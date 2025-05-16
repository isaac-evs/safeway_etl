import psycopg2
from psycopg2.extras import execute_values
import logging
from config import DB_CONFIG

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.conn = None
        self.cursor = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.conn.autocommit = False
            self.cursor = self.conn.cursor()
            logger.info("Database connection established successfully")
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            raise

    def disconnect(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def initialize_db(self):
        try:
            self.connect()
            self.cursor.execute("""
            CREATE EXTENSION IF NOT EXISTS postgis;

            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                news_source TEXT,
                title TEXT,
                description TEXT,
                coordinates GEOGRAPHY(POINT, 4326),
                type TEXT CHECK (type IN ('crime', 'infrastructure', 'hazard', 'social')),
                date DATE,
                url TEXT UNIQUE,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS news_coordinates_idx ON news USING GIST(coordinates);
            CREATE INDEX IF NOT EXISTS news_type_idx ON news(type);
            CREATE INDEX IF NOT EXISTS news_date_idx ON news(date);
            """)
            self.conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            if self.conn:
                self.conn.rollback()
            raise
        finally:
            self.disconnect()

    def insert_article(self, article):
        try:
            self.connect()
            self.cursor.execute("""
            INSERT INTO news (news_source, title, description, coordinates, type, date, url)
            VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s)
            ON CONFLICT (url) DO NOTHING
            RETURNING id
            """, (
                article['news_source'],
                article['title'],
                article['description'],
                article['coordinates'][0],
                article['coordinates'][1],
                article['type'],
                article['date'],
                article['url']
            ))
            result = self.cursor.fetchone()
            self.conn.commit()
            if result:
                logger.info(f"Inserted article with ID: {result[0]}")
                return result[0]
            else:
                logger.info(f"Article already exists in database: {article['title']}")
                return None
        except Exception as e:
            logger.error(f"Error inserting article: {e}")
            if self.conn:
                self.conn.rollback()
            raise
        finally:
            self.disconnect()

    def get_processed_urls(self):
        try:
            self.connect()
            self.cursor.execute("SELECT url FROM news")
            urls = {row[0] for row in self.cursor.fetchall()}
            return urls
        except Exception as e:
            logger.error(f"Error fetching processed URLs: {e}")
            return set()
        finally:
            self.disconnect()

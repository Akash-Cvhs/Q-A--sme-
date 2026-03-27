import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_DB = os.getenv("POSTGRES_DB", "healthcare_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
schema_name = os.getenv("schema_name", "insurance")


def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor()
        cursor.execute(f"SET search_path TO {schema_name}, public")
        cursor.close()
        return conn
    except Exception as e:
        print(f"⚠️ DB error: {e}")
        return None
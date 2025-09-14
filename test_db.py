import os
import psycopg2
from dotenv import load_dotenv

# Load .env file
load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )
    print("✅ Database connection successful!")

    cur = conn.cursor()
    cur.execute("SELECT NOW();")  # simple test query
    result = cur.fetchone()
    print("🕒 Database time is:", result[0])

    cur.close()
    conn.close()
except Exception as e:
    print("❌ Database connection failed:")
    print(e)

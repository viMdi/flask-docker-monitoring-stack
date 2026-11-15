import os
import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)


def get_db_connection():
	return psycopg2.connect(
		dbname=os.getenv("DB_NAME"),
		user=os.getenv("DB_USER"),
		password=os.getenv("DB_PASSWORD"),
		host="psqldatabases",
		port="5432",
		connect_timeout=3,
	)


def init_db():
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		cursor.execute("""
			CREATE TABLE IF NOT EXISTS checks (
				id SERIAL PRIMARY KEY,
				url TEXT NOT NULL,
				status_code INTEGER,
				is_up BOOLEAN NOT NULL,
				created_at TIMESTAMP DEFAULT NOW()
			);
		""")
		conn.commit()
		cursor.close()
		conn.close()
	except Exception as e:
		print(f"Database error: {e}")


init_db()


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    url = None
    history = []

    if request.method == "POST":
        url = (
            request.form.get("url", "")
            .strip()
            .replace("https://", "")
            .replace("http://", "")
        )
        if url:
            status_code = None
            is_up = False
            try:
                response = requests.get("https://" + url, timeout=5)
                status_code = response.status_code

                if response.status_code < 400:
                    is_up = True
                    result = f"Сайт доступен (Код: {response.status_code})"
                else:
                    result = f"Ошибка (Код: {response.status_code})"
            except Exception:
                result = "Ошибка: сайт недоступен или не существует"

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO checks (url, status_code, is_up) VALUES (%s, %s, %s)",
                    (url, status_code, is_up),
                )
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"DB insert error: {e}")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT url, status_code, created_at "
            "FROM checks "
            "ORDER BY created_at DESC LIMIT 5"
        )
        history = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DB select error: {e}")

    return render_template("index.html", result=result, url=url, history=history)


import os
import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    url = None

    if request.method == "POST":
        url = (
            request.form.get("url", "")
            .strip()
            .replace("https://", "")
            .replace("http://", "")
        )
        if url:
            try:
                response = requests.get("https://" + url, timeout=5)

                if response.status_code < 400:
                    result = f"Сайт доступен (Код: {response.status_code})"
                else:
                    result = f"Ошибка (Код: {response.status_code})"
            except Exception:
                result = "Ошибка: сайт недоступен или не существует"

    return render_template("index.html", result=result, url=url)


@app.route("/db-test", methods=["GET"])
def dtbase():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host="psqldatabases",
            port="5432",
            connect_timeout=3,
        )

        cursor = conn.cursor()

        cursor.execute("SELECT 1;")

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        return jsonify({"database": "connected"})

    except Exception as e:
        return jsonify({"database": "error", "details": str(e)}), 500

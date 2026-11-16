import os
import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-uptimeguard")


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
                ip_address VARCHAR(45),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("""
            ALTER TABLE checks
      		ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);
        """)

        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")


init_db()


def send_telegram_alert(url, status_code):
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")

    if not token or not chat_id:
        return

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    text = f"🚨 {url} is down! HTTP status: {status_code or 'No response'}"

    try:
        requests.post(
            api_url,
            json = {"chat_id": chat_id, "text": text},
            timeout = 5
        )
    except Exception as e:
        print(f"Telegram error: {e}")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_ip = request.headers.get("X-Real-IP", request.remote_addr)
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
                    result = f"Сайт {url} доступен (Код: {response.status_code})"
                else:
                    result = f"Сайт {url} вернул ошибку (Код: {response.status_code})"
                    send_telegram_alert(url, response.status_code)
            except Exception:
                result = f"Ошибка: сайт {url} недоступен или не существует"
                send_telegram_alert(url, None)

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO checks (url, status_code, is_up, ip_address) VALUES (%s, %s, %s, %s)",
                    (url, status_code, is_up, user_ip),
                )
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"DB insert error: {e}")

            flash(result)

        return redirect(url_for("index"))

    history = []
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

    return render_template("index.html", history=history)


@app.route("/db-test", methods=["GET"])
def dtbase():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        cursor.fetchone()
        cursor.close()
        conn.close()

        return jsonify({"database": "connected"})

    except Exception as e:
        return jsonify({"database": "error", "details": str(e)}), 500

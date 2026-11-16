import os, psycopg2, requests, socket, ipaddress
from urllib.parse import urlparse
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


def is_safe_url(url):
	if not url.startswith(("http://", "https://")):
		url = "http://" + url

	parsed = urlparse(url)
	hostname = parsed.hostname

	if not hostname:
		return False

	try:
		ip_str = socket.gethostbyname(hostname)
	except socket.gaierror:
		return False

	try:
		ip_obj = ipaddress.ip_address(ip_str)
	except ValueError:
		return False, "Некорректный адрес сайта."

	if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
		return False, "Недопустимый адрес."

	return True, None


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

		cursor.execute("""
			CREATE TABLE IF NOT EXISTS monitors (
				id SERIAL PRIMARY KEY,
				url TEXT NOT NULL UNIQUE,
				telegram_chat_id TEXT NOT NULL,
				is_active BOOLEAN DEFAULT TRUE,
				last_check TIMESTAMP
			);
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


@app.route("/dashboard", methods=["GET"])
def dashboard():
	monitors = []
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		cursor.execute(
			"SELECT id, url, telegram_chat_id, is_active, last_check "
			"FROM monitors ORDER BY id DESC"
		)
		monitors = cursor.fetchall()
		cursor.close()
		conn.close()
	except Exception as e:
		print(f"DB dashboard select error: {e}")

	return render_template("dashboard.html", monitors=monitors)


@app.route("/add_monitor", methods=["POST"])
def add_monitor():
	url = (
		request.form.get("url", "")
		.strip()
		.replace("https://", "")
		.replace("http://", "")
	)
	telegram_chat_id = request.form.get("telegram_chat_id", "").strip()

	if url and telegram_chat_id:
		try:
			conn = get_db_connection()
			cursor = conn.cursor()
			cursor.execute(
				"INSERT INTO monitors (url, telegram_chat_id) VALUES (%s, %s)",
				(url, telegram_chat_id),
			)
			conn.commit()
			cursor.close()
			conn.close()
			flash(f"Сайт {url} успешно добавлен в мониторинг!", "success")
		except Exception as e:
			print(f"DB add_monitor error: {e}")
			flash(f"Ошибка: возможно, сайт {url} уже есть в списке.", "error")

	return redirect(url_for("dashboard"))


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
			is_safe, error_msg = is_safe_url(url)
			if not is_safe:
				flash(error_msg, "error")
				return redirect(url_for("index"))

			status_code = None
			is_up = False
			headers = {
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UptimeGuard/1.0"
			}

			try:
				try:
					response = requests.get("https://" + url, timeout=5, headers=headers)

				except requests.exceptions.RequestException:
					response = requests.get("http://" + url, timeout=5, headers=headers)

				status_code = response.status_code

				if response.status_code < 400:
					is_up = True
					result = f"Сайт {url} доступен (Код: {response.status_code})"
					flash(result, "success")
				else:
					result = f"Сайт {url} вернул ошибку (Код: {response.status_code})"
					send_telegram_alert(url, response.status_code)
					flash(result, "error")
			except Exception:
				result = f"Ошибка: сайт {url} недоступен или не существует"
				send_telegram_alert(url, None)
				flash(result, "error")

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

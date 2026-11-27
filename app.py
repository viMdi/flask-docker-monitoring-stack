import os, psycopg2, requests
from urllib.parse import urlparse
from dotenv import load_dotenv
from flask import Flask, flash, session, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from utils import is_safe_url, check_site_availability


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-uptimeguard")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.session_protection = "strong"


class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM users WHERE id = %s;", (int(user_id),))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return User(id=row[0], username=row[1])
        return None
    except Exception as e:
        print(f"DB load_user error: {e}")
        return None


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host="psqldatabases",
        port="5432",
        connect_timeout=3,
    )


def if_safe_next(target):
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/") and not target.startswith("//")


def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(64) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

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
            CREATE TABLE IF NOT EXISTS monitors (
                id SERIAL PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                telegram_chat_id TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                last_check TIMESTAMP
            );
        """)

        cursor.execute("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS user_id INTEGER;")

        cursor.execute("""
            DO $$
            BEGIN
                ALTER TABLE monitors ADD CONSTRAINT fk_monitors_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

        cursor.execute("ALTER TABLE monitors DROP CONSTRAINT IF EXISTS monitors_url_key;")

        cursor.execute("""
            DO $$
            BEGIN
                ALTER TABLE monitors ADD CONSTRAINT uq_monitors_user_url UNIQUE (user_id, url);
            EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
            END $$;
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
        requests.post(api_url, json={"chat_id": chat_id, "text": text}, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not (3 <= len(username) <= 32):
            flash("Логин должен быть от 3 до 32 символов.", "error")
            return render_template("register.html")

        if not (6 <= len(password) <= 128):
            flash("Пароль должен быть от 6 до 128 символов.", "error")
            return render_template("register.html")

        if not (any(char.isalpha() for char in password) and any(char.isdigit() for char in password)):
            flash("Пароль должен содержать хотя бы одну букву и одну цифру.", "error")
            return render_template("register.html")

        password_hash = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s);",
                (username, password_hash),
            )
            conn.commit()
            flash("Регистрация успешна! Теперь войдите.", "success")
            return redirect(url_for("login"))

        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash("Такой логин уже занят", "error")
            return render_template("register.html")

        finally:
            cursor.close()
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_page = request.args.get("next") or request.form.get("next")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s;",
            (username,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row and check_password_hash(row[2], password):
            session.clear()
            login_user(User(id=row[0], username=row[1]))

            if if_safe_next(next_page):
                return redirect(next_page)

            return redirect(url_for("dashboard"))

        flash("Неверный логин или пароль", "error")

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Вы вышли из системы.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    monitors = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, url, telegram_chat_id, is_active, last_check FROM monitors WHERE user_id = %s ORDER BY id DESC",
            (current_user.id,),
        )
        monitors = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DB dashboard select error: {e}")

    return render_template("dashboard.html", monitors=monitors)


@app.route("/add_monitor", methods=["POST"])
@login_required
def add_monitor():
    url = request.form.get("url", "").strip().replace("https://", "").replace("http://", "")
    telegram_chat_id = request.form.get("telegram_chat_id", "").strip()

    if url and telegram_chat_id:
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO monitors (user_id, url, telegram_chat_id) VALUES (%s, %s, %s)",
                (current_user.id, url, telegram_chat_id),
            )
            conn.commit()
            flash(f"Сайт {url} успешно добавлен в мониторинг!", "success")

        except psycopg2.errors.UniqueViolation:
            if conn:
                conn.rollback()
            flash(f"Ошибка: сайт {url} уже есть в вашем списке.", "error")

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"DB add_monitor error: {e}")
            flash("Произошла ошибка при добавлении сайта.", "error")

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return redirect(url_for("dashboard"))


@app.route("/delete_monitor/<int:monitor_id>", methods=["POST"])
@login_required
def delete_monitor(monitor_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM monitors WHERE id = %s and user_id = %s;",
            (monitor_id, current_user.id),
        )
        conn.commit()
        flash("Монитор удалён.", "success")
    except Exception as e:
        conn.rollback()
        print(f"DB delete_monitor error: {e}")
        flash("Ошибка при удалении.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("dashboard"))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_ip = request.headers.get("X-Real-IP", request.remote_addr)
        url = request.form.get("url", "").strip().replace("https://", "").replace("http://", "")

        if url:
            is_safe, result_data = is_safe_url(url)
            if not is_safe:
                flash(result_data, "error")
                return redirect(url_for("index"))

            checked_ip = result_data
            status_code = None
            is_up = False

            response, error_msg = check_site_availability(url, checked_ip)

            if response:
                status_code = response.status_code
                if status_code < 400:
                    is_up = True
                    result = f"Сайт {url} доступен (Код: {status_code})"
                    flash(result, "success")
                else:
                    result = f"Сайт {url} вернул ошибку (Код: {status_code})"
                    send_telegram_alert(url, status_code)
                    flash(result, "error")
            else:
                result = f"Ошибка: сайт {url} недоступен. Детали: {error_msg}"
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
        cursor.execute("SELECT url, status_code, created_at FROM checks ORDER BY created_at DESC LIMIT 5")
        history = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DB select error: {e}")

    return render_template("index.html", history=history)


@app.route("/db-test", methods=["GET"])
@login_required
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

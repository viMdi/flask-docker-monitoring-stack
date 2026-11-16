import os, psycopg2, requests, time, socket, ipaddress
from urllib.parse import urlparse


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
        return False, "Некорректный адрес сайта."

    try:
        ip_str = socket.gethostbyname(hostname)
    except (socket.gaierror, UnicodeError):
        return False, "Домен не найден. Проверьте правильность написания."

    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, "Ошибка при обработке IP-адреса."

    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
        return False, "Запросы к локальной сети запрещены из соображений безопасности."

    return True, None


def send_alert(url, status_code, chat_id):
    token = os.getenv("TG_BOT_TOKEN")

    if not token or not chat_id:
        return

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    text = f"🚨 {url} is down! HTTP status: {status_code or 'No response'}"

    try:
        requests.post(
            api_url,
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except Exception as e:
        print(f"Telegram alert error: {e}")


def check_all():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, url, telegram_chat_id FROM monitors WHERE is_active = TRUE;"
        )
        monitors = cursor.fetchall()

        for monitor in monitors:
            monitor_id, url, chat_id = monitor

            is_safe, error_msg = is_safe_url(url)
            if not is_safe:
                print(f"[BLOCKED] {url} - {error_msg}")
                continue

            status_code = None
            is_up = False

            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UptimeGuard/1.0"}
                try:
                    response = requests.get("https://" + url, timeout=10, headers=headers)
                except requests.exceptions.RequestException:
                    response = requests.get("http://" + url, timeout=10, headers=headers)

                status_code = response.status_code

                if response.status_code < 400:
                    is_up = True
                    print(f"[OK] {url} (Status: {status_code})")
                else:
                    print(f"[DOWN] {url} (Status: {status_code})")
                    send_alert(url, status_code, chat_id)
            except Exception as e:
                print(f"[ERROR] {url} is unreachable: {e}")
                send_alert(url, None, chat_id)

            cursor.execute(
                "INSERT INTO checks (url, status_code, is_up) VALUES (%s, %s, %s);",
                (url, status_code, is_up),
            )
            cursor.execute(
                "UPDATE monitors SET last_check = NOW() WHERE id = %s;",
                (monitor_id,),
            )
            conn.commit()

    except Exception as e:
        print(f"Worker DB error: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    print("Background checker started...")
    while True:
        check_all()
        time.sleep(60)

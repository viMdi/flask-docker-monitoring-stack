import ipaddress
import socket
import requests
from urllib.parse import urlparse
from requests_toolbelt.adapters import host_header_ssl


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
        return False, "Укажите публичный IP-адрес или домен."

    return True, ip_str


def check_site_availability(url, checked_ip):
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    parsed = urlparse(url)
    scheme = parsed.scheme
    hostname = parsed.hostname
    port = parsed.port
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""

    ip_netloc = checked_ip
    if port:
        ip_netloc = f"{checked_ip}:{port}"

    target_url = f"{scheme}://{ip_netloc}{path}{query}"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UptimeGuard/1.0", "Host": hostname}

    session = requests.Session()
    session.mount("https://", host_header_ssl.HostHeaderSSLAdapter())

    try:
        response = session.get(target_url, headers=headers, timeout=5, allow_redirects=False)
        return response, None
    except Exception as e:
        return None, str(e)

# mylab: Веб-сервис с автоматизацией и мониторингом

Проект представляет собой личную лабораторию (homelab) для отработки практик Infrastructure as Code, контейнеризации и мониторинга. Включает в себя развертывание веб-приложения, настройку пайплайна CI/CD, системы мониторинга с алертингом и автоматического резервного копирования.

## Архитектура проекта

Вся инфраструктура запускается с помощью Docker Compose:
- Web-приложение: Python (Flask) + Gunicorn
- Веб-сервер: Nginx (выступает в роли reverse proxy)
- База данных: PostgreSQL (используется Volume для сохранения данных)
- Мониторинг: Prometheus, Node Exporter, Nginx Exporter
- Визуализация: Grafana
- Оповещения: Alertmanager (интеграция с Telegram)

## Реализованный функционал

- [x] Контейнеризация: Все компоненты изолированы в Docker.
- [x] CI/CD: Настроен GitHub Actions (сборка Docker-образа и пуш в GitHub Container Registry).
- [x] Мониторинг: Сбор метрик с хоста и Nginx, построение дашбордов в Grafana, отправка алертов в Telegram.
- [x] Резервное копирование: Автоматический дамп базы данных (pg_dump) по расписанию (Cron) с очисткой старых архивов.
- [x] Безопасность: Защита SSH от брутфорса с помощью fail2ban.

## Стек технологий

- ОС: Debian 12 (VirtualBox)
- Контейнеризация: Docker, Docker Compose
- CI/CD: GitHub Actions
- Веб: Nginx, Python (Flask, Gunicorn)
- Базы данных: PostgreSQL
- Мониторинг: Prometheus, Grafana, Alertmanager
- Скрипты: Bash, Python

## Запуск проекта

1. Клонировать репозиторий:
   git clone https://github.com/viMdi/flask_hlab.git
2. Создать файл .env на основе .env.example и указать свои значения (секреты не хранятся в репозитории).
3. Запустить инфраструктуру:
   docker compose up -d --build
4. Проверить статус контейнеров:
   docker compose ps

## Проверка работы

- Главная страница: GET http://localhost/
- Проверка связи с базой данных: GET http://localhost/db-test

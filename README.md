# Daily Check-in Bot

MVP Telegram-бот для ежедневных отметок (селфи) с напоминаниями и эскалацией доверенным контактам.

## Что входит
- FastAPI webhook сервис
- Celery worker для фоновых задач
- Scheduler сервис (rolling window для постановки задач)
- PostgreSQL + Redis
- Alembic миграции

## Быстрый старт (локально)
```bash
cp .env.example .env
# заполните переменные

# Миграции
alembic upgrade head

# Запуск
docker compose -f infra/docker-compose.yml up --build
```

## Переменные окружения
См. `.env.example`.

## Деплой в Timeweb (App Platform + managed Postgres/Redis)
1) Создайте managed PostgreSQL и Redis в Timeweb.cloud.
2) Создайте приложения:
   - `api` (Dockerfile: `infra/Dockerfile.api`)
   - `worker` (Dockerfile: `infra/Dockerfile.worker`)
   - `scheduler` (Dockerfile: `infra/Dockerfile.scheduler`) — запуск по расписанию.
3) Пропишите переменные окружения для каждого сервиса:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_WEBHOOK_SECRET`
   - `PUBLIC_BASE_URL` (https URL, где доступен `api`)
   - `DATABASE_URL`
   - `REDIS_URL`
   - `CELERY_BROKER_URL` (обычно = `REDIS_URL`)
   - `CELERY_RESULT_BACKEND` (например `redis://.../1`)
4) Включите webhook (бот выставит его автоматически при старте, если задан `PUBLIC_BASE_URL`).
5) Настройте запуск `scheduler` по расписанию (каждые 30–60 минут). Если в App Platform нет scheduled jobs, используйте VM с cron только для scheduler.

## Логика
- Scheduler создает `daily_state` на 36 часов вперед и ставит `checkin_due` задачи с ETA.
- `checkin_due` ставит напоминания (T+30, T+60, T+90) и дедлайн.
- `deadline_missed` отправляет эскалацию доверенным контактам.
- При поздней отметке бот спрашивает, уведомлять ли контакты о том, что пользователь на связи.

## Команды в боте
- `/start`
- `/set_timezone Europe/Moscow`
- `/set_time 09:30`
- `/add_contact` (дальше переслать сообщение контакта)
- `/pause 1d` или `/pause 1w`
- `/disable`
- `/status`

## Замечания по безопасности
- Храните токен бота и доступы к БД/Redis в секретах App Platform.
- Для S3 включите `STORE_MEDIA_IN_S3=true` и заполните S3 переменные.

## Миграции
```bash
alembic upgrade head
```

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from celery import Celery

from daily_checkin.config import settings
from daily_checkin.db import session_scope
from daily_checkin.models import DailyStateEnum, UserStatus
from daily_checkin.repositories import (
    CheckinRepository,
    DailyStateRepository,
    NotificationLogRepository,
    UserRepository,
)
from daily_checkin.services.notifications import (
    notify_contacts_last_checkin,
    notify_contacts_online,
    send_contact_consent_request,
)
from daily_checkin.storage import upload_bytes
from daily_checkin.utils_time import add_minutes

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError

celery_app = Celery(
    "daily_checkin",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.enable_utc = True
celery_app.conf.timezone = "UTC"


@celery_app.task(name="tasks.checkin_due")
def checkin_due(user_id: int, date_local: str | None = None):
    with session_scope() as session:
        users = UserRepository(session)
        states = DailyStateRepository(session)
        user = users.get_by_id(user_id)
        if not user:
            return

        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        if user.status == UserStatus.PAUSED:
            if user.pause_until and user.pause_until <= now:
                user.status = UserStatus.ACTIVE
            else:
                return
        if user.status != UserStatus.ACTIVE:
            return

        tz = ZoneInfo(user.timezone)
        if not date_local:
            date_local = datetime.utcnow().astimezone(tz).date().isoformat()

        state = states.get_state(user.id, datetime.fromisoformat(date_local).date())
        if not state or state.state != DailyStateEnum.PENDING:
            return

        celery_app.send_task(
            "tasks.reminder", args=[user.id, date_local, 1], eta=add_minutes(state.due_at_utc, 30)
        )
        celery_app.send_task(
            "tasks.reminder", args=[user.id, date_local, 2], eta=add_minutes(state.due_at_utc, 60)
        )
        celery_app.send_task(
            "tasks.reminder", args=[user.id, date_local, 3], eta=add_minutes(state.due_at_utc, 90)
        )
        celery_app.send_task(
            "tasks.deadline_missed", args=[user.id, date_local], eta=state.deadline_at_utc
        )


@celery_app.task(name="tasks.reminder")
def reminder(user_id: int, date_local: str, n: int):
    with session_scope() as session:
        users = UserRepository(session)
        states = DailyStateRepository(session)
        logs = NotificationLogRepository(session)

        user = users.get_by_id(user_id)
        if not user or user.status != UserStatus.ACTIVE:
            return
        state = states.get_state(user_id, datetime.fromisoformat(date_local).date())
        if not state or state.state != DailyStateEnum.PENDING:
            return
        if state.reminders_sent_count >= n:
            return

        key = f"reminder:{user_id}:{date_local}:{n}"
        if not logs.try_insert(key, "REMINDER", user_id, user.tg_chat_id):
            return

        from daily_checkin.telegram.bot import create_bot
        import asyncio

        bot = create_bot()
        text = "Напоминание: пора сделать отметку (селфи)."
        try:
            asyncio.run(bot.send_message(user.tg_chat_id, text))
            logs.mark_sent(key)
            states.increment_reminders(user_id, datetime.fromisoformat(date_local).date())
        except TelegramForbiddenError as exc:
            logs.mark_error(key, "FORBIDDEN", str(exc))
            _mark_unreachable(user_id)
        except TelegramRetryAfter as exc:
            logs.mark_error(key, "RATE_LIMIT", str(exc))
            raise
        except TelegramAPIError as exc:
            logs.mark_error(key, "API_ERROR", str(exc))
        except Exception as exc:
            logs.mark_error(key, "SEND_ERROR", str(exc))


@celery_app.task(name="tasks.deadline_missed")
def deadline_missed(user_id: int, date_local: str):
    with session_scope() as session:
        states = DailyStateRepository(session)
        logs = NotificationLogRepository(session)
        users = UserRepository(session)
        user = users.get_by_id(user_id)
        if not user:
            return
        state = states.get_state(user_id, datetime.fromisoformat(date_local).date())
        if not state or state.state != DailyStateEnum.PENDING:
            return

        key = f"deadline:{user_id}:{date_local}"
        if not logs.try_insert(key, "DEADLINE", user_id, user.tg_chat_id):
            return

        state_date = datetime.fromisoformat(date_local).date()
        states.mark_missed(user_id, state_date)
        states.set_escalation_sent(user_id, state_date, datetime.utcnow())

    notify_contacts_last_checkin(user_id, reason="Пропуск ежедневной отметки.")


@celery_app.task(name="tasks.unreachable_recheck")
def unreachable_recheck(user_id: int):
    with session_scope() as session:
        users = UserRepository(session)
        states = DailyStateRepository(session)
        user = users.get_by_id(user_id)
        if not user or not user.unreachable_since:
            return

        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        if user.unreachable_since + timedelta(hours=settings.unreachable_recheck_hours) > now:
            return

    notify_contacts_last_checkin(
        user_id,
        reason="Пользователь недоступен/возможно удалил или заблокировал бота.",
    )


@celery_app.task(name="tasks.send_contact_consent_request")
def send_contact_consent_request_task(user_id: int, contact_id: int):
    send_contact_consent_request(user_id, contact_id)


@celery_app.task(name="tasks.send_online_status")
def send_online_status(user_id: int, date_local: str):
    notify_contacts_online(user_id, when_text=date_local)


@celery_app.task(name="tasks.send_late_checkin_prompt")
def send_late_checkin_prompt(user_id: int, date_local: str):
    with session_scope() as session:
        users = UserRepository(session)
        states = DailyStateRepository(session)
        logs = NotificationLogRepository(session)
        user = users.get_by_id(user_id)
        if not user:
            return
        state = states.get_state(user_id, datetime.fromisoformat(date_local).date())
        if not state or state.late_prompt_response_at is not None:
            return

        key = f"late_prompt:{user_id}:{date_local}"
        if not logs.try_insert(key, "LATE_PROMPT", user_id, user.tg_chat_id):
            return

        from daily_checkin.telegram.bot import create_bot
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        import asyncio

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Да", callback_data=f"late_notify:yes:{date_local}")
        kb.button(text="❌ Нет", callback_data=f"late_notify:no:{date_local}")

        text = (
            "Вы отметились после дедлайна. Сообщить контактам, что вы на связи?"
        )

        try:
            asyncio.run(create_bot().send_message(user.tg_chat_id, text, reply_markup=kb.as_markup()))
            logs.mark_sent(key)
            states.mark_late_prompt_sent(user_id, datetime.fromisoformat(date_local).date(), datetime.utcnow())
        except TelegramForbiddenError as exc:
            logs.mark_error(key, "FORBIDDEN", str(exc))
            _mark_unreachable(user_id)
        except Exception as exc:
            logs.mark_error(key, "SEND_ERROR", str(exc))


@celery_app.task(name="tasks.store_media_s3")
def store_media_s3(checkin_id: int, file_id: str):
    if not settings.store_media_in_s3:
        return
    from daily_checkin.telegram.bot import create_bot
    import asyncio

    bot = create_bot()
    try:
        file = asyncio.run(bot.get_file(file_id))
        file_bytes = asyncio.run(bot.download_file(file.file_path))
    except Exception:
        return

    if hasattr(file_bytes, "read"):
        data = file_bytes.read()
    else:
        data = file_bytes

    key = f"checkins/{checkin_id}/{file_id}.jpg"
    upload_bytes(data, key, "image/jpeg")

    with session_scope() as session:
        checkins = CheckinRepository(session)
        checkins.set_photo_s3_key(checkin_id, key)


def _mark_unreachable(user_id: int):
    with session_scope() as session:
        users = UserRepository(session)
        user = users.get_by_id(user_id)
        if not user:
            return
        if user.unreachable_since:
            return
        users.set_unreachable(user_id, datetime.utcnow().replace(tzinfo=timezone.utc))

    celery_app.send_task(
        "tasks.unreachable_recheck",
        args=[user_id],
        eta=datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(hours=settings.unreachable_recheck_hours),
    )

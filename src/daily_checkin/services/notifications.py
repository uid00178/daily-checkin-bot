from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from redis import Redis

from ..config import settings
from ..db import session_scope
from ..models import TrustedContact
from ..repositories import CheckinRepository, ContactRepository, NotificationLogRepository, UserRepository
from ..telegram.rate_limiter import RateLimiter


redis_client = Redis.from_url(settings.redis_url)
rate_limiter = RateLimiter(redis_client, settings.telegram_rate_limit_per_sec)


async def _send_message(bot: Bot, chat_id: int, text: str, reply_markup=None):
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def _send_photo(bot: Bot, chat_id: int, file_id: str, caption: str):
    await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)


def _run_async(coro):
    return asyncio.run(coro)


def send_contact_consent_request(user_id: int, contact_id: int):
    with session_scope() as session:
        users = UserRepository(session)
        contact = session.get(TrustedContact, contact_id)
        user = users.get_by_id(user_id)
        if not contact or not user:
            return

    bot = Bot(token=settings.telegram_bot_token)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=f"contact_:approve_{contact_id}")
    kb.button(text="❌ Нет", callback_data=f"contact_:decline_{contact_id}")

    text = (
        "Пользователь добавил вас как доверенный контакт.\n"
        "Согласны получать уведомления при пропуске отметки?"
    )

    _run_async(_send_message(bot, contact.contact_chat_id, text, kb.as_markup()))


def notify_contacts_last_checkin(user_id: int, reason: str):
    with session_scope() as session:
        contacts_repo = ContactRepository(session)
        checkins = CheckinRepository(session)
        logs = NotificationLogRepository(session)
        contacts = contacts_repo.list_approved(user_id)
        last = checkins.latest_for_user(user_id)

        if not contacts:
            return

        bot = Bot(token=settings.telegram_bot_token)

        for contact in contacts:
            key = f"escalation:{user_id}:{contact.contact_chat_id}:{reason}"
            if not logs.try_insert(key, "ESCALATION", user_id, contact.contact_chat_id):
                continue

            text = "Пользователь не отметился вовремя. " + reason
            if last:
                text += f"\nПоследняя отметка: {last.created_at}"
                if last.geo_lat is not None and last.geo_lon is not None:
                    text += f"\nГео: {last.geo_lat}, {last.geo_lon}"
            try:
                if last:
                    _run_async(_send_photo(bot, contact.contact_chat_id, last.photo_file_id, text))
                else:
                    _run_async(_send_message(bot, contact.contact_chat_id, text))
                logs.mark_sent(key)
            except Exception as exc:
                logs.mark_error(key, "SEND_ERROR", str(exc))


def notify_contacts_online(user_id: int, when_text: str):
    with session_scope() as session:
        contacts_repo = ContactRepository(session)
        logs = NotificationLogRepository(session)
        contacts = contacts_repo.list_approved(user_id)

        if not contacts:
            return

        bot = Bot(token=settings.telegram_bot_token)

        for contact in contacts:
            key = f"online:{user_id}:{contact.contact_chat_id}:{when_text}"
            if not logs.try_insert(key, "ONLINE", user_id, contact.contact_chat_id):
                continue

            text = f"Пользователь снова на связи: {when_text}"
            try:
                _run_async(_send_message(bot, contact.contact_chat_id, text))
                logs.mark_sent(key)
            except Exception as exc:
                logs.mark_error(key, "SEND_ERROR", str(exc))

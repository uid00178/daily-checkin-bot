from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone

from aiogram import Router, F
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from zoneinfo import ZoneInfo

from ..db import session_scope
from ..config import settings
from ..repositories import (
    CheckinRepository,
    ContactRepository,
    DailyStateRepository,
    UserRepository,
)
from ..models import ContactStatus, UserStatus
from ..services.scheduler import enqueue_checkin_due
from ..services.state_machine import record_checkin
from ..services.tasks import store_media_s3, send_online_status

router = Router()


@router.message(Command("start"))
async def start_cmd(message: Message):
    with session_scope() as session:
        users = UserRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if user:
            await message.answer(
                "Вы уже зарегистрированы. Используйте /status, /set_time HH:MM и /set_timezone <IANA>."
            )
            return
        await message.answer(
            "Привет! Это бот ежедневных отметок.\n"
            "Шаг 1: укажи таймзону командой /set_timezone (например, Europe/Moscow).\n"
            "Шаг 2: укажи время отметки командой /set_time HH:MM (например, 09:30)."
        )


@router.message(Command("set_timezone"))
async def set_timezone(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /set_timezone Europe/Moscow")
        return
    tz_name = parts[1].strip()
    try:
        ZoneInfo(tz_name)
    except Exception:
        await message.answer("Неизвестная таймзона. Пример: Europe/Moscow")
        return

    with session_scope() as session:
        users = UserRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            await message.answer("Сначала укажите время: /set_time HH:MM")
            return
        user.timezone = tz_name
        await message.answer("Таймзона сохранена.")


@router.message(Command("set_time"))
async def set_time(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /set_time 09:30")
        return
    value = parts[1].strip()
    try:
        hh, mm = value.split(":")
        t = dtime(hour=int(hh), minute=int(mm))
    except Exception:
        await message.answer("Формат: /set_time 09:30")
        return

    with session_scope() as session:
        users = UserRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            user = users.create_user(
                tg_user_id=message.from_user.id,
                tg_chat_id=message.chat.id,
                timezone="UTC",
                checkin_time_local=t,
            )
        else:
            user.checkin_time_local = t

        await message.answer(
            "Время сохранено. Укажите таймзону: /set_timezone Europe/Moscow"
        )

        enqueue_checkin_due(user.id)


@router.message(Command("pause"))
async def pause_cmd(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1] not in {"1d", "1w"}:
        await message.answer("Формат: /pause 1d или /pause 1w")
        return
    delta = timedelta(days=1) if parts[1] == "1d" else timedelta(days=7)
    until = datetime.utcnow().replace(tzinfo=timezone.utc) + delta

    with session_scope() as session:
        users = UserRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            await message.answer("Сначала /start")
            return
        user.pause_until = until
        user.status = UserStatus.PAUSED

    await message.answer("Пауза включена.")


@router.message(Command("disable"))
async def disable_cmd(message: Message):
    with session_scope() as session:
        users = UserRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            await message.answer("Сначала /start")
            return
        user.status = UserStatus.DISABLED
    await message.answer("Сервис отключен.")


@router.message(Command("add_contact"))
async def add_contact(message: Message):
    await message.answer(
        "Добавьте контакт пересылкой сообщения этого человека в боте."
    )


@router.message(F.forward_from)
async def add_contact_forward(message: Message):
    with session_scope() as session:
        users = UserRepository(session)
        contacts = ContactRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            await message.answer("Сначала настройте время и таймзону.")
            return
        if contacts.count_for_user(user.id) >= 5:
            await message.answer("Лимит контактов: 5.")
            return
        contact_user = message.forward_from
        contact = contacts.create_contact(
            user_id=user.id,
            contact_tg_user_id=contact_user.id,
            contact_chat_id=contact_user.id,
        )
        await message.answer(
            "Запрос согласия отправлен контакту. Он должен подтвердить получение информации."
        )

    from ..services.tasks import send_contact_consent_request

    send_contact_consent_request.delay(user.id, contact.id)


@router.message(Command("status"))
async def status_cmd(message: Message):
    with session_scope() as session:
        users = UserRepository(session)
        states = DailyStateRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            await message.answer("Пользователь не найден. /start")
            return
        today = datetime.utcnow().astimezone(ZoneInfo(user.timezone)).date()
        state = states.get_state(user.id, today)
        if not state:
            await message.answer("Сегодняшний статус еще не создан.")
            return
        await message.answer(
            f"Статус: {state.state}\n"
            f"Напоминаний отправлено: {state.reminders_sent_count}\n"
            f"Дедлайн (UTC): {state.deadline_at_utc}"
        )


@router.message(F.content_type == ContentType.PHOTO)
async def checkin_photo(message: Message):
    with session_scope() as session:
        users = UserRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            await message.answer("Сначала /start")
            return

        photo = message.photo[-1]
        checkin = record_checkin(
            session=session,
            user=user,
            photo_file_id=photo.file_id,
        )

        if settings.store_media_in_s3:
            store_media_s3.delay(checkin.id, photo.file_id)

    await message.answer("Отметка сохранена. Спасибо!")


@router.message(F.content_type == ContentType.LOCATION)
async def checkin_geo(message: Message):
    with session_scope() as session:
        users = UserRepository(session)
        checkins = CheckinRepository(session)
        user = users.get_by_tg_user_id(message.from_user.id)
        if not user:
            await message.answer("Сначала /start")
            return
        recent = checkins.latest_within(user.id, minutes=5)
        if not recent:
            await message.answer("Нет свежей отметки, чтобы прикрепить геолокацию.")
            return
        checkins.attach_geo(recent.id, message.location.latitude, message.location.longitude)
    await message.answer("Геолокация добавлена.")


@router.callback_query(F.data.startswith("contact_"))
async def contact_consent(callback: CallbackQuery):
    try:
        action, contact_id = callback.data.split(":", 1)[1].split("_", 1)
    except ValueError:
        await callback.answer("Неверный запрос")
        return

    status = ContactStatus.APPROVED if action == "approve" else ContactStatus.DECLINED

    with session_scope() as session:
        contacts = ContactRepository(session)
        contacts.set_status(int(contact_id), status)

    await callback.message.answer("Спасибо, ваш выбор сохранен.")
    await callback.answer()


@router.callback_query(F.data.startswith("late_notify:"))
async def late_notify_callback(callback: CallbackQuery):
    try:
        _, action, date_local = callback.data.split(":", 2)
    except ValueError:
        await callback.answer("Неверный запрос")
        return

    notify = action == "yes"
    with session_scope() as session:
        users = UserRepository(session)
        states = DailyStateRepository(session)
        user = users.get_by_tg_user_id(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден")
            return
        states.set_late_response(user.id, datetime.fromisoformat(date_local).date(), notify)

    if notify:
        send_online_status.delay(user.id, date_local)

    await callback.message.answer("Готово, ваш ответ сохранен.")
    await callback.answer()

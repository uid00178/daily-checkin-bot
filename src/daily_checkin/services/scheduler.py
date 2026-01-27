from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from celery import Celery

from ..config import settings
from ..db import session_scope
from ..repositories import DailyStateRepository, UserRepository
from ..models import UserStatus
from ..utils_time import combine_local_to_utc, add_minutes

celery_app = Celery(
    "daily_checkin",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.enable_utc = True
celery_app.conf.timezone = "UTC"


def enqueue_checkin_due(user_id: int):
    celery_app.send_task("tasks.checkin_due", args=[user_id])


def schedule_window():
    with session_scope() as session:
        users_repo = UserRepository(session)
        states = DailyStateRepository(session)
        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        window_end = now_utc + timedelta(hours=settings.scheduler_window_hours)

        for user in users_repo.list_all():
            if user.status == UserStatus.PAUSED and user.pause_until:
                if user.pause_until <= now_utc:
                    user.status = UserStatus.ACTIVE
                else:
                    continue
            if user.status != UserStatus.ACTIVE:
                continue
            tz = ZoneInfo(user.timezone)
            local_start = now_utc.astimezone(tz).date()
            local_end = window_end.astimezone(tz).date()
            current = local_start
            while current <= local_end:
                due_at = combine_local_to_utc(user.timezone, current, user.checkin_time_local)
                deadline_at = add_minutes(due_at, 90)
                states.upsert_state(user.id, current, due_at, deadline_at)
                celery_app.send_task("tasks.checkin_due", args=[user.id, current.isoformat()], eta=due_at)
                current = current + timedelta(days=1)

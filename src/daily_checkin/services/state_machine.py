from __future__ import annotations

from datetime import datetime, timezone

from ..repositories import CheckinRepository, DailyStateRepository
from ..models import DailyStateEnum
from ..utils_time import combine_local_to_utc, local_date_for, add_minutes, add_hours
from ..config import settings
from .tasks import send_late_checkin_prompt


def record_checkin(session, user, photo_file_id: str):
    states = DailyStateRepository(session)
    checkins = CheckinRepository(session)

    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    local_date = local_date_for(user.timezone, now_utc)

    state = states.get_state(user.id, local_date)
    if not state:
        due_at = combine_local_to_utc(user.timezone, local_date, user.checkin_time_local)
        deadline_at = add_minutes(due_at, 90)
        state = states.upsert_state(user.id, local_date, due_at, deadline_at)

    is_late = now_utc > state.deadline_at_utc

    checkin = checkins.create_checkin(
        user_id=user.id,
        date_local=local_date,
        photo_file_id=photo_file_id,
        photo_s3_key=None,
        is_late=is_late,
    )

    if state.state == DailyStateEnum.PENDING:
        states.mark_done(user.id, local_date)

    if (
        is_late
        and state.state == DailyStateEnum.MISSED
        and state.escalation_sent_at is not None
        and now_utc <= add_hours(state.deadline_at_utc, settings.checkin_grace_hours)
    ):
        send_late_checkin_prompt.delay(user.id, local_date.isoformat())

    return checkin

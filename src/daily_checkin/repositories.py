from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select, update, insert
from sqlalchemy.exc import IntegrityError

from .models import (
    Checkin,
    ContactStatus,
    DailyState,
    DailyStateEnum,
    NotificationLog,
    TrustedContact,
    User,
    UserStatus,
)


class UserRepository:
    def __init__(self, session):
        self.session = session

    def get_by_tg_user_id(self, tg_user_id: int) -> User | None:
        return self.session.execute(
            select(User).where(User.tg_user_id == tg_user_id)
        ).scalar_one_or_none()

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()

    def create_user(
        self, tg_user_id: int, tg_chat_id: int, timezone: str, checkin_time_local
    ) -> User:
        user = User(
            tg_user_id=tg_user_id,
            tg_chat_id=tg_chat_id,
            timezone=timezone,
            checkin_time_local=checkin_time_local,
            status=UserStatus.ACTIVE,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def list_active(self) -> list[User]:
        return (
            self.session.execute(select(User).where(User.status == UserStatus.ACTIVE))
            .scalars()
            .all()
        )

    def list_all(self) -> list[User]:
        return self.session.execute(select(User)).scalars().all()

    def set_unreachable(self, user_id: int, since: datetime):
        self.session.execute(
            update(User).where(User.id == user_id).values(unreachable_since=since)
        )


class ContactRepository:
    def __init__(self, session):
        self.session = session

    def count_for_user(self, user_id: int) -> int:
        return (
            self.session.execute(select(TrustedContact).where(TrustedContact.user_id == user_id))
            .scalars()
            .all()
        ).__len__()

    def create_contact(self, user_id: int, contact_tg_user_id: int, contact_chat_id: int):
        contact = TrustedContact(
            user_id=user_id,
            contact_tg_user_id=contact_tg_user_id,
            contact_chat_id=contact_chat_id,
            status=ContactStatus.PENDING,
        )
        self.session.add(contact)
        self.session.flush()
        return contact

    def set_status(self, contact_id: int, status: ContactStatus):
        self.session.execute(
            update(TrustedContact)
            .where(TrustedContact.id == contact_id)
            .values(status=status)
        )

    def list_approved(self, user_id: int) -> list[TrustedContact]:
        return (
            self.session.execute(
                select(TrustedContact).where(
                    TrustedContact.user_id == user_id,
                    TrustedContact.status == ContactStatus.APPROVED,
                )
            )
            .scalars()
            .all()
        )


class CheckinRepository:
    def __init__(self, session):
        self.session = session

    def create_checkin(
        self,
        user_id: int,
        date_local: date,
        photo_file_id: str,
        photo_s3_key: str | None,
        is_late: bool,
    ) -> Checkin:
        checkin = Checkin(
            user_id=user_id,
            date_local=date_local,
            photo_file_id=photo_file_id,
            photo_s3_key=photo_s3_key,
            is_late=is_late,
        )
        self.session.add(checkin)
        self.session.flush()
        return checkin

    def attach_geo(self, checkin_id: int, lat: float, lon: float):
        self.session.execute(
            update(Checkin).where(Checkin.id == checkin_id).values(geo_lat=lat, geo_lon=lon)
        )

    def set_photo_s3_key(self, checkin_id: int, key: str):
        self.session.execute(
            update(Checkin).where(Checkin.id == checkin_id).values(photo_s3_key=key)
        )

    def latest_for_user(self, user_id: int) -> Checkin | None:
        return (
            self.session.execute(
                select(Checkin)
                .where(Checkin.user_id == user_id)
                .order_by(Checkin.created_at.desc())
            )
            .scalars()
            .first()
        )

    def latest_within(self, user_id: int, minutes: int) -> Checkin | None:
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        return (
            self.session.execute(
                select(Checkin)
                .where(Checkin.user_id == user_id, Checkin.created_at >= threshold)
                .order_by(Checkin.created_at.desc())
            )
            .scalars()
            .first()
        )


class DailyStateRepository:
    def __init__(self, session):
        self.session = session

    def upsert_state(self, user_id: int, date_local: date, due_at_utc, deadline_at_utc):
        existing = self.session.execute(
            select(DailyState).where(
                DailyState.user_id == user_id, DailyState.date_local == date_local
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        state = DailyState(
            user_id=user_id,
            date_local=date_local,
            due_at_utc=due_at_utc,
            deadline_at_utc=deadline_at_utc,
            state=DailyStateEnum.PENDING,
            reminders_sent_count=0,
        )
        self.session.add(state)
        self.session.flush()
        return state

    def get_state(self, user_id: int, date_local: date) -> DailyState | None:
        return self.session.execute(
            select(DailyState).where(
                DailyState.user_id == user_id, DailyState.date_local == date_local
            )
        ).scalar_one_or_none()

    def mark_done(self, user_id: int, date_local: date):
        self.session.execute(
            update(DailyState)
            .where(DailyState.user_id == user_id, DailyState.date_local == date_local)
            .values(state=DailyStateEnum.DONE)
        )

    def increment_reminders(self, user_id: int, date_local: date):
        self.session.execute(
            update(DailyState)
            .where(DailyState.user_id == user_id, DailyState.date_local == date_local)
            .values(reminders_sent_count=DailyState.reminders_sent_count + 1)
        )

    def mark_missed(self, user_id: int, date_local: date):
        self.session.execute(
            update(DailyState)
            .where(DailyState.user_id == user_id, DailyState.date_local == date_local)
            .values(state=DailyStateEnum.MISSED)
        )

    def set_escalation_sent(self, user_id: int, date_local: date, sent_at: datetime):
        self.session.execute(
            update(DailyState)
            .where(DailyState.user_id == user_id, DailyState.date_local == date_local)
            .values(escalation_sent_at=sent_at)
        )

    def mark_late_prompt_sent(self, user_id: int, date_local: date, sent_at: datetime):
        self.session.execute(
            update(DailyState)
            .where(DailyState.user_id == user_id, DailyState.date_local == date_local)
            .values(late_prompt_sent_at=sent_at)
        )

    def set_late_response(self, user_id: int, date_local: date, notify: bool):
        self.session.execute(
            update(DailyState)
            .where(DailyState.user_id == user_id, DailyState.date_local == date_local)
            .values(late_prompt_response_at=datetime.utcnow(), late_notify_contacts=notify)
        )


class NotificationLogRepository:
    def __init__(self, session):
        self.session = session

    def try_insert(self, key: str, type_: str, user_id: int, target_chat_id: int) -> bool:
        try:
            self.session.execute(
                insert(NotificationLog).values(
                    idempotency_key=key,
                    type=type_,
                    user_id=user_id,
                    target_chat_id=target_chat_id,
                    status="PENDING",
                )
            )
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def mark_sent(self, key: str):
        self.session.execute(
            update(NotificationLog)
            .where(NotificationLog.idempotency_key == key)
            .values(status="SENT", sent_at=datetime.utcnow())
        )

    def mark_error(self, key: str, code: str, message: str):
        self.session.execute(
            update(NotificationLog)
            .where(NotificationLog.idempotency_key == key)
            .values(status="ERROR", error_code=code, error_message=message)
        )

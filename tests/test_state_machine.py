from datetime import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from daily_checkin.models import Base, User, UserStatus
from daily_checkin.services.state_machine import record_checkin
from daily_checkin.repositories import DailyStateRepository, CheckinRepository


def test_record_checkin_marks_done():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        user = User(
            tg_user_id=1,
            tg_chat_id=1,
            timezone="UTC",
            checkin_time_local=time(9, 0),
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        session.commit()

        record_checkin(session, user, "file_123")

        checkins = CheckinRepository(session)
        assert checkins.latest_for_user(user.id) is not None

        states = DailyStateRepository(session)
        # The state should exist for today
        from datetime import datetime, timezone as tz

        today = datetime.now(tz.utc).date()
        state = states.get_state(user.id, today)
        assert state is not None
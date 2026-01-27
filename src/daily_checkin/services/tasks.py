from __future__ import annotations

from celery import Celery

from ..config import settings

celery_app = Celery(
    "daily_checkin",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


class TaskProxy:
    def __init__(self, name: str):
        self.name = name

    def delay(self, *args, **kwargs):
        return celery_app.send_task(self.name, args=args, kwargs=kwargs)


send_contact_consent_request = TaskProxy("tasks.send_contact_consent_request")
send_late_checkin_prompt = TaskProxy("tasks.send_late_checkin_prompt")
store_media_s3 = TaskProxy("tasks.store_media_s3")
send_online_status = TaskProxy("tasks.send_online_status")

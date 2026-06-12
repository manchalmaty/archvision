from celery import Celery

from config import settings

celery_app = Celery(
    "archvision",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["core.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

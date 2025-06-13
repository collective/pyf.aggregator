from celery import Celery

import os

load_dotenv()

app = Celery(
    "pyf-aggregator",
    broker=os.getenv('REDIS_HOST'),
    broker_connection_retry_on_startup=True,
)
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from pyf.aggregator.logger import logger

import os


load_dotenv()

app = Celery(
    "pyf-aggregator",
    broker=os.getenv('REDIS_HOST'),
    broker_connection_retry_on_startup=True,
)


#### Celery tasks

@app.task
def inspect_project(package_data):
    """
    Inspect a project and insert if matching

    Args:
        package_data (str): The data of the project.
    """
    logger.info(f"Inspect package: {package_data}")
    # TODO (reduce also log above)

@app.task
def update_project(package_id):
    """
    Process a package release data.

    Args:
        package_id (str): The ID of the package.
    """
    logger.info(f"Processing {package_id}")
    # TODO

@app.task
def update_github(package_id):
    """
    Process a package release data.

    Args:
        package_id (str): The ID of the package.
    """
    logger.info(f"Processing {package_id}")
    # TODO

@app.task
def read_rss_new_projects_and_queue():
    # TODO
    pass

@app.task
def read_rss_new_releases_and_queue():
    # TODO
    pass

@app.task
def queue_all_github_updates():
    # TODO
    pass

####  Celery periodic tasks

@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kw):
    """
    Setup periodic tasks for the Celery app.
    """
    sender.add_periodic_task(
        crontab(minute="*/1", hour="*"),
        read_rss_new_projects_and_queue.s(),
        name='read RSS new projects and add to queue'
    )
    sender.add_periodic_task(
        crontab(minute="*/1", hour="*"),
        read_rss_new_releases_and_queue.s(),
        name='read RSS new releases and add to queue'
    )
    pass
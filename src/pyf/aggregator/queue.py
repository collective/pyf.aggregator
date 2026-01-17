from celery import Celery
from .logger import logger
from celery.schedules import crontab
import os


load_dotenv()

app = Celery(
    "pyf-aggregator",
    broker=os.getenv('REDIS_HOST'),
    broker_connection_retry_on_startup=True,
)


#### Celery tasks

@app.task
def inspect_project(project_data):
    """
    Fetch project JSON info, Inspect and insert if matching

    Args:
        agg (Aggregator): Aggregator object
        project_data (dict): With `_last_serial` and `name` of the project.
    """
    logger.info(f"Inspect package: {project_data}")
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
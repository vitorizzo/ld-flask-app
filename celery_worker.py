from tools.app_factory import create_app
from config.celery_app import init_celery, celery

app = create_app()
init_celery(app)

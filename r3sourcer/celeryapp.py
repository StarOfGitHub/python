import os
import dotenv

from celery import Celery
from django.conf import settings  # noqa

dotenv.read_dotenv(".env_defaults")
dotenv.read_dotenv(".env", override=True)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'r3sourcer.settings.prod')

app = Celery('r3sourcer')
app.config_from_object('r3sourcer.celeryconfig')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

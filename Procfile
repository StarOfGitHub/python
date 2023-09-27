runserver: PYTHONUNBUFFERED=true django runserver 0.0.0.0:$DJANGO_UWSGI_PORT
celery: celery worker -n worker.celery -A r3sourcer -E -l info --scheduler=redbeat.RedBeatScheduler -Q celery,sms,hr
celery_beat: celery beat -A r3sourcer -l info --scheduler=redbeat.RedBeatScheduler

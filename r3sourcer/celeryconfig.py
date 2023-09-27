import os

from celery.schedules import crontab
from kombu import Queue, Exchange


def env(key, default=None):
    return os.environ.get(key, default)


result_backend = 'django-db'

broker_url = 'amqp://{host}:{port}//'.format(
    host=env('RABBIT_MQ_HOST'),
    port=env('RABBIT_MQ_PORT'),
)
redbeat_redis_url = 'redis://{host}:{port}/{db}'.format(
    host=env('REDIS_HOST'),
    port=env('REDIS_PORT'),
    db=env('REDIS_BEAT_DB'),
)

timezone = 'UTC'
enable_utc = True
accept_content = ['json', 'application/text']
broker_transport_options = {'visibility_timeout': 2 * 60 * 60}
broker_pool_limit = None

task_queues = (
    Queue('celery', Exchange('celery'), routing_key='celery'),
    Queue('sms', Exchange('sms'), routing_key='sms'),
    Queue('hr', Exchange('hr'), routing_key='hr'),
)

task_routes = {
    'r3sourcer.apps.sms_interface.tasks.fetch_remote_sms': {
        'queue': 'sms',
    },
}

beat_schedule = {
    'fetch_twilio_accounts': {
        'task': 'r3sourcer.apps.sms_interface.tasks.fetch_remote_sms',
        'schedule': crontab(minute=5),
    },
    'check_unpaid_invoices': {
        'task': 'r3sourcer.apps.hr.tasks.check_unpaid_invoices',
        'schedule': crontab(hour=5, minute=00),
    },
    'update_all_distances': {
        'task': 'r3sourcer.apps.hr.tasks.update_all_distances',
        'schedule': crontab(minute=0, hour=22, day_of_week='fri,sat')
    },
    'close_not_active_jobsites': {
        'task': 'r3sourcer.apps.hr.tasks.close_not_active_jobsites',
        'schedule': crontab(minute=4, hour=0)
    },
    'fetch_payments': {
        'task': 'r3sourcer.apps.billing.tasks.fetch_payments',
        'schedule': crontab(minute=30)
    },
    'sync_subscriptions': {
        'task': 'r3sourcer.apps.billing.tasks.sync_subscriptions',
        'schedule': crontab(hour=3)
    },
    'charge_for_extra_workers': {
        'task': 'r3sourcer.apps.billing.tasks.charge_for_extra_workers',
        'schedule': crontab(hour=1)
    },
    'send_sms_payment_reminder': {
        'task': 'r3sourcer.apps.billing.tasks.send_sms_payment_reminder',
        'schedule': crontab(minute=45)
    },
    'restrict_access_for_users_without_subscription': {
        'task': 'r3sourcer.apps.billing.tasks.restrict_access_for_users_without_subscription',
        'schedule': crontab(minute=35, hour=3)
    },
    'update_superannuation_fund_list': {
        'task': 'r3sourcer.apps.candidate.tasks.update_superannuation_fund_list',
        'schedule': crontab(minute=0, hour=0, day_of_month=2)
    },
    'generate_invoices': {
        'task': 'r3sourcer.apps.hr.tasks.generate_invoices',
        'schedule': crontab(minute=0, hour=3)
    },
    'check_carrier_list': {
        'task': 'r3sourcer.apps.hr.tasks.check_carrier_list',
        'schedule': crontab(minute=4, hour='10-22')
    },
    'delete_old_shifts': {
        'task': 'r3sourcer.apps.hr.tasks.delete_old_shifts',
        'schedule': crontab(minute=30, hour=1)
    },
}

task_ignore_result = True
task_store_errors_even_if_ignored = True

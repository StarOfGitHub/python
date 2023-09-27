from celery import shared_task

from r3sourcer.apps.email_interface.utils import get_email_service


@shared_task(name='send_email_default')
def send_email_default(recipients, subject=None, text_message=None, email_tpl=None, *args, **kwargs):
    email_service = get_email_service()

    if email_tpl is not None:
        # propagate master company
        email_service.send_tpl(recipients, subject, tpl_name=email_tpl, *args, **kwargs)
    else:
        email_service.send(recipients, subject, text_message, *args, **kwargs)

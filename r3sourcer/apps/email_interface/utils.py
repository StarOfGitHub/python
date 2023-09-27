import importlib

from django.conf import settings


def get_email_service(email_service_class=None, *args, **kwargs):
    if not email_service_class:
        is_email_service_enabled = getattr(settings, 'EMAIL_SERVICE_ENABLED', True)
        email_service_class = 'r3sourcer.apps.email_interface.services.FakeEmailService'

        if is_email_service_enabled:
            email_service_class = getattr(settings, 'EMAIL_SERVICE_CLASS', email_service_class)

    class_name = email_service_class.split('.')[-1]

    EmailServiceClass = getattr(importlib.import_module(
        email_service_class.rsplit('.', 1)[0]
    ), class_name)

    return EmailServiceClass(*args, **kwargs)

import importlib

from django.conf import settings


def get_sms_service(sms_service_class=None, *args, **kwargs):
    if not sms_service_class:
        is_sms_service_enabled = getattr(settings,
                                         'SMS_SERVICE_ENABLED',
                                         True)
        sms_service_class = 'r3sourcer.apps.sms_interface.services.FakeSMSService'
        if is_sms_service_enabled:
            sms_service_class = getattr(settings,
                                        'SMS_SERVICE_CLASS',
                                        sms_service_class)
    class_name = sms_service_class.split('.')[-1]

    SMSSeriveClass = getattr(importlib.import_module(
        sms_service_class.rsplit('.', 1)[0]
    ), class_name)

    return SMSSeriveClass(*args, **kwargs)

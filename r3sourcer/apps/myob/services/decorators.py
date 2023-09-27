from django.conf import settings


def myob_enabled_mode(func):
    def fake_handler(*args, **kwargs):
        pass

    def wrapper(*args, **kwargs):
        if settings.ENABLED_MYOB_WORKING:
            return func(*args, **kwargs)
        return fake_handler(*args, **kwargs)

    return wrapper

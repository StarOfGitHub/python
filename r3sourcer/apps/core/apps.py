from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class CoreConfig(AppConfig):
    name = 'r3sourcer.apps.core'
    label = 'core'

    def ready(self):
        from r3sourcer.apps.core.api.router import router

        try:
            from modeltranslation.models import autodiscover
            autodiscover()
        except ImportError:
            pass

        autodiscover_modules('endpoints', register_to=router)

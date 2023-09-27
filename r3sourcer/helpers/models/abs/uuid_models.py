import uuid

from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.apps.core.managers import AbstractObjectOwnerManager
from r3sourcer.apps.logger.main import endless_logger


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(verbose_name=_("Updated at"), auto_now=True, editable=False)
    created_at = models.DateTimeField(verbose_name=_("Created at"), auto_now_add=True, editable=False)

    objects = AbstractObjectOwnerManager()

    class Meta:
        abstract = True

    @classmethod
    def use_logger(cls):
        return True

    @classmethod
    def is_owned(cls):
        return True

    @classmethod
    def owner_lookups(cls, owner):
        return []

    @classmethod
    def owned_by_lookups(cls, owner):
        return None

    @property
    def object_history(self):
        return endless_logger.get_object_history(self.__class__, self.pk)

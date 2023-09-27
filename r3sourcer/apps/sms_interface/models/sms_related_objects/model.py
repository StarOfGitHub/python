from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import UUIDModel


class SMSRelatedObject(UUIDModel):
    """
    Related object for SMSMessage.
    """

    sms = models.ForeignKey(
        'sms_interface.SMSMessage',
        on_delete=models.CASCADE,
        verbose_name=_("SMS message"),
        related_name='related_objects'
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey()

    def __str__(self):
        return '{}: {}'.format(self.content_type.name, self.content_object)

    class Meta:
        verbose_name = _("SMS related object")
        verbose_name_plural = _("SMS related objects")

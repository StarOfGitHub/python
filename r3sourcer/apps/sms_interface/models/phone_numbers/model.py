from django.db import models
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import UUIDModel


class PhoneNumber(UUIDModel):

    sid = models.CharField(
        max_length=254,
        verbose_name=_("SID"),
        unique=True,
        editable=False,
        help_text=_("Number ID"),
    )
    phone_number = models.CharField(
        max_length=32,
        verbose_name=_("Phone"),
    )
    friendly_name = models.CharField(
        max_length=512,
        default="",
        editable=False,
        verbose_name=_("Friendly name"),
    )
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
        related_name='phone_numbers'
    )

    # capabilities
    sms_enabled = models.BooleanField(
        default=True,
        verbose_name=_("SMS enabled"),
    )
    mms_enabled = models.BooleanField(
        default=True,
        verbose_name=_("MMS enabled"),
    )
    voice_enabled = models.BooleanField(
        default=True,
        verbose_name=_("VOICE enabled"),
    )

    is_default = models.BooleanField(
        verbose_name=_("Using as default for company"),
        default=False
    )

    def __str__(self):
        return self.phone_number

    class Meta:
        verbose_name = _("Phone number")
        verbose_name_plural = _("Phone numbers")


def disable_default_flag_for_phones(**kwargs):
    """
    Disable is_default value for all phone numbers if instance

    :param kwargs:
    :return:
    """
    if kwargs['instance'].is_default:
        kwargs['instance'].company.phone_numbers.exclude(id=kwargs['instance'].id).update(is_default=False)


post_save.connect(disable_default_flag_for_phones, sender=PhoneNumber)

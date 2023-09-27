from django.db import models
from django.utils.translation import ugettext_lazy as _
from model_utils import Choices


class BankAccountLayout(models.Model):
    MYOB = 'MYOB'
    OTHER = 'OTHER'
    PAYMENT_TYPES = Choices(
        (MYOB, _("MYOB payment system")),
        (OTHER, _("Other payment system")),
    )
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=32, unique=True)
    description = models.CharField(max_length=128)
    payment_system = models.CharField(
        max_length=25,
        verbose_name=_("Payment system"),
        choices=PAYMENT_TYPES,
        default=OTHER
    )

    class Meta:
        verbose_name = _("Bank account layout")
        verbose_name_plural = _("Bank account layouts")

    def __str__(self):
        return self.name

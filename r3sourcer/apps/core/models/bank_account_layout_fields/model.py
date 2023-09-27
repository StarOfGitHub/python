from django.db import models
from django.utils.translation import ugettext_lazy as _


class BankAccountLayoutField(models.Model):
    field = models.ForeignKey(
        'core.BankAccountField',
        related_name="layouts",
        verbose_name=_("Bank account field"),
        on_delete=models.CASCADE)
    layout = models.ForeignKey(
        'core.BankAccountLayout',
        related_name="fields",
        verbose_name=_("Bank account layout"),
        on_delete=models.PROTECT)
    order = models.SmallIntegerField(default=0)
    required = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Bank account layout field")
        verbose_name_plural = _("Bank account layout fields")
        unique_together = (("field", "layout"),)

from django.db import models
from django.utils.translation import ugettext_lazy as _


class BankAccountFieldLanguage(models.Model):
    name = models.CharField(max_length=64)
    ba_field = models.ForeignKey(
        'core.BankAccountField',
        related_name="languages",
        verbose_name=_("Bank account field language"),
        on_delete=models.CASCADE)
    language = models.ForeignKey(
        'core.Language',
        related_name="bank_account_fields",
        verbose_name=_("Language"),
        on_delete=models.PROTECT)

    default = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Bank account field language")
        verbose_name_plural = _("Bank account field languages")
        unique_together = (("ba_field", "language"),)

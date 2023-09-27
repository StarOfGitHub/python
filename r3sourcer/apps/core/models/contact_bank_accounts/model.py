from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import UUIDModel


class ContactBankAccount(UUIDModel):
    contact = models.ForeignKey(
        'core.Contact',
        related_name="bank_accounts",
        on_delete=models.CASCADE,
        verbose_name="Contact"
    )
    layout = models.ForeignKey(
        'core.BankAccountLayout',
        on_delete=models.PROTECT,
        verbose_name='Layout'
    )

    class Meta:
        verbose_name = _("Contact Bank account")
        verbose_name_plural = _("Contact Bank accounts")

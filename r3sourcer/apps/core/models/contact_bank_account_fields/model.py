from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import UUIDModel


class ContactBankAccountField(UUIDModel):
    bank_account = models.ForeignKey(
        'core.ContactBankAccount',
        related_name="fields",
        on_delete=models.CASCADE,
        verbose_name="Bank account"
    )
    field = models.ForeignKey(
        'core.BankAccountField',
        on_delete=models.PROTECT,
        verbose_name='Field'
    )
    value = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        verbose_name = _("Contact Bank account field")
        verbose_name_plural = _("Contact Bank account fields")

    def save(self, *args, **kwargs):
        layout_field = self.bank_account.layout.fields.get(field_id=self.field_id)
        if layout_field.required is True and not self.value:
            raise ValueError('Field with id {field_id} is required'.format(field_id=self.field_id))
        super().save(*args, **kwargs)

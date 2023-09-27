from django.db import models
from django.utils.translation import ugettext_lazy as _


class BankAccountLayoutCountry(models.Model):
    country = models.ForeignKey(
        'core.Country',
        related_name="layouts",
        verbose_name=_("Country"),
        to_field='code2',
        on_delete=models.CASCADE)
    layout = models.ForeignKey(
        'core.BankAccountLayout',
        related_name="countries",
        verbose_name=_("Bank account layout"),
        on_delete=models.PROTECT)
    default = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Bank account layout country")
        verbose_name_plural = _("Bank account layout countries")
        unique_together = (("country", "layout"),)

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):

        if self.default is True:
            BankAccountLayoutCountry.objects.filter(layout=self.layout, default=True).update(default=False)

        super().save(force_insert, force_update, using, update_fields)

from django.db import models
from django.utils.translation import ugettext_lazy as _

from ...fields import AliasField


class Language(models.Model):
    alpha_2 = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=64)
    id = AliasField(db_column='alpha_2', unique=True)

    class Meta:
        verbose_name = _("Language")
        verbose_name_plural = _("Languages")

    def __str__(self):
        return self.name

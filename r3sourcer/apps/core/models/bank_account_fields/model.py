from django.db import models
from django.utils.translation import ugettext_lazy as _


class BankAccountField(models.Model):
    name = models.SlugField(max_length=32, unique=True)
    description = models.CharField(max_length=128)

    class Meta:
        verbose_name = _("Bank account field")
        verbose_name_plural = _("Bank account fields")

    def __str__(self):
        return self.name

    def translation(self, language):
        """ SkillName translation getter """
        try:
            return self.languages.get(language=language).name
        except:
            pass
        try:
            return self.languages.get(language_id='en').name
        except:
            return self.name

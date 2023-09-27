from django.db import models
from django.utils.translation import ugettext_lazy as _

from model_utils import Choices
from r3sourcer.helpers.models.abs import UUIDModel, TimeZoneUUIDModel
from r3sourcer.apps.core.models import Language


class UnitOfMeasurement(UUIDModel):

    name = models.CharField(_("Unit name"), max_length=32, unique=True)
    short_name = models.CharField(_("Unit short name"), max_length=16, unique=True)
    default = models.BooleanField(_("Default unit of measurement"), default=False)

    class Meta:
        verbose_name = _("Unit of measurement")
        verbose_name_plural = _("Units of measurement")

    def __str__(self):
        return self.name

    def translation(self, language):
        try:
            return self.translations.get(language=language).name
        except:
            return self.name

    def short_name_translation(self, language):
        try:
            return self.translations.get(language=language).short_name
        except:
            return self.short_name


class UOMLanguage(models.Model):
    uom = models.ForeignKey(UnitOfMeasurement, verbose_name=_('Unit of measurement'),
                            on_delete=models.CASCADE, related_name='translations')
    language = models.ForeignKey(Language, verbose_name=_("Language"),
                                 on_delete=models.CASCADE, related_name='uomlanguages')
    name = models.CharField(_("UOM name translation"), max_length=16)
    short_name = models.CharField(_("UOM short name translation"), max_length=16)

    class Meta:
        verbose_name = _("UOM translations")
        unique_together = [
            'uom',
            'language',
        ]

    def __str__(self):
        return str(self.language)

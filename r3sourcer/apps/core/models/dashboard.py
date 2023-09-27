from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import UUIDModel

__all__ = [
    'DashboardModule',
    'UserDashboardModule'
]


class DashboardModule(UUIDModel):

    content_type = models.OneToOneField(
        'contenttypes.ContentType',
        verbose_name=_("Model"),
        unique=True,
        related_name='+',
        on_delete=models.CASCADE,
    )

    is_active = models.BooleanField(
        _("Is active"),
        default=True
    )

    endpoint = models.CharField(
        max_length=255,
        verbose_name=_('Endpoint'),
    )

    description = models.CharField(
        max_length=255,
        verbose_name=_('Description'),
        null=True,
        blank=True
    )

    add_label = models.CharField(
        max_length=64,
        verbose_name=_('Add button label'),
        null=True,
        blank=True
    )

    label = models.CharField(
        max_length=64,
        verbose_name=_('Button label'),
        null=True,
        blank=True
    )

    @classmethod
    def is_owned(cls):
        return False

    def __str__(self):
        return str(self.content_type)

    class Meta:
        verbose_name = _("Dashboard module")
        verbose_name_plural = _("Dashboard modules")
        permissions = (
            ('can_use_module', _("Can use this module")),
        )


class UserDashboardModule(UUIDModel):

    company_contact = models.ForeignKey(
        'core.CompanyContact',
        verbose_name=_("Company contact"),
        related_name='dashboard_modules',
        on_delete=models.CASCADE,
    )

    dashboard_module = models.ForeignKey(
        'DashboardModule',
        verbose_name=_("Dashboard module"),
        related_name='dashboard_modules',
        on_delete=models.CASCADE,
    )

    position = models.PositiveIntegerField(
        verbose_name=_("position"),
        help_text=_("would be used for ordering")
    )

    ui_config = JSONField(
        verbose_name=_("UI config"),
        default={},
        blank=True
    )

    def __str__(self):
        return '{company_contact}: {module}'.format(
            company_contact=self.company_contact,
            module=self.dashboard_module,
        )

    # @classmethod
    # def is_owned(cls):
    #     return False

    def is_available(self):
        return self.dashboard_module.is_active

    class Meta:
        ordering = ['company_contact', '-position']
        unique_together = ('company_contact', 'dashboard_module')
        verbose_name = _("User dashboard module")
        verbose_name_plural = _("User dashboard modules")

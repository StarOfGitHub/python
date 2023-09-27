from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import TemplateMessage


class SMSTemplate(TemplateMessage):
    SMS = 'sms'
    TYPE_CHOICES = (
        (SMS, _("SMS")),
    )

    type = models.CharField(
        max_length=8,
        choices=TYPE_CHOICES,
        default=SMS,
        verbose_name=_("Type")
    )

    company = models.ForeignKey(
        'core.Company',
        verbose_name=_("Master company"),
        on_delete=models.CASCADE,
        related_name='sms_templates',
        null=True,
        blank=True
    )
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Template language"),
        on_delete=models.CASCADE,
        related_name='sms_templates',
    )

    subject_template = ''
    message_html_template = ''

    class Meta:
        verbose_name = _("SMS Template")
        verbose_name_plural = _("SMS Templates")
        ordering = ['name']
        unique_together = [
            'company',
            'name',
            'slug',
            'language',
        ]

    def __str__(self):
        return f'{self.name}'

from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import DefaultTemplateABS
from ..sms_templates import SMSTemplate


class DefaultSMSTemplate(DefaultTemplateABS):
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Language"),
        on_delete=models.PROTECT,
        related_name='default_sms_templates',
        db_index=True,
    )

    class Meta:
        verbose_name = _("Default SMS Template")
        verbose_name_plural = _("Default SMS Templates")
        unique_together = (('slug', 'language'),)
        ordering = ['name']

    def save(self, *args, **kwargs):
        from r3sourcer.apps.core.models import Company
        super().save(*args, **kwargs)

        SMSTemplate.objects.\
            filter(slug=self.slug, language_id=self.language.alpha_2).\
            update(message_text_template=self.message_text_template)

        templates = []
        companies = Company.objects.filter(type=Company.COMPANY_TYPES.master,
                                           languages__language=self.language)
        for company in companies:
            if not SMSTemplate.objects.filter(company=company,
                                              slug=self.slug,
                                              language=self.language):
                obj = SMSTemplate(
                    name=self.name,
                    slug=self.slug,
                    message_text_template=self.message_text_template,
                    reply_timeout=self.reply_timeout,
                    delivery_timeout=self.delivery_timeout,
                    language_id=self.language.alpha_2,
                    company_id=company.id)
                templates.append(obj)
        SMSTemplate.objects.bulk_create(templates)

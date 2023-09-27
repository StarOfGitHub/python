from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _

from r3sourcer.apps.email_interface.models import EmailTemplate, DefaultEmailTemplate
from r3sourcer.apps.sms_interface.models import DefaultSMSTemplate, SMSTemplate


class CompanyLanguage(models.Model):
    company = models.ForeignKey(
        'core.Company',
        related_name="languages",
        verbose_name=_("Company"),
        on_delete=models.CASCADE)

    language = models.ForeignKey(
        'core.Language',
        related_name="company_languages",
        verbose_name=_("Language"),
        on_delete=models.PROTECT)

    default = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Company language")
        verbose_name_plural = _("Company languages")
        unique_together = (("company", "language"),)

    def __str__(self):
        return self.language.name

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):

        if self.default is True:
            CompanyLanguage.objects.filter(company=self.company, default=True).update(default=False)

        super().save(force_insert, force_update, using, update_fields)

        if self.company.type == self.company.COMPANY_TYPES.master:
            sms_templates = SMSTemplate.objects.filter(
                language=self.language,
                company=self.company
            ).all()
            default_sms_templates = DefaultSMSTemplate.objects.filter(
                language=self.language
            ).exclude(slug__in=[x.slug for x in sms_templates]).all()
            if not default_sms_templates:
                default_sms_templates = DefaultSMSTemplate.objects.filter(
                    language_id=settings.DEFAULT_LANGUAGE
                ).exclude(slug__in=[x.slug for x in sms_templates]).all()
            new_sms_templates = []
            for sms_template in default_sms_templates:
                obj = SMSTemplate(
                    name=sms_template.name,
                    slug=sms_template.slug,
                    message_text_template=sms_template.message_text_template,
                    reply_timeout=sms_template.reply_timeout,
                    delivery_timeout=sms_template.delivery_timeout,
                    language_id=self.language_id,
                    company_id=self.company_id)
                new_sms_templates.append(obj)
            SMSTemplate.objects.bulk_create(new_sms_templates)

            email_templates = EmailTemplate.objects.filter(
                language=self.language,
                company=self.company
            ).all()
            default_email_templates = DefaultEmailTemplate.objects.filter(
                language=self.language
            ).exclude(slug__in=[x.slug for x in email_templates]).all()
            if not default_email_templates:
                default_email_templates = DefaultEmailTemplate.objects.filter(
                    language_id=settings.DEFAULT_LANGUAGE
                ).exclude(slug__in=[x.slug for x in email_templates]).all()
            new_email_templates = []
            for email_template in default_email_templates:
                obj = EmailTemplate(
                    name=email_template.name,
                    slug=email_template.slug,
                    subject_template=email_template.subject_template,
                    message_text_template=email_template.message_text_template,
                    message_html_template=email_template.message_html_template,
                    reply_timeout=email_template.reply_timeout,
                    delivery_timeout=email_template.delivery_timeout,
                    language_id=self.language_id,
                    company_id=self.company_id)
                new_email_templates.append(obj)
            EmailTemplate.objects.bulk_create(new_email_templates)

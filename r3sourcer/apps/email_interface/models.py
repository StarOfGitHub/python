from django.db import models
from django.utils.translation import ugettext_lazy as _
from filer.models import File

from model_utils import Choices

from r3sourcer.helpers.models.abs import TemplateMessage, UUIDModel, DefaultTemplateABS, TimeZoneUUIDModel

TEXT_CONTENT_TYPE = 'text/plain'
HTML_CONTENT_TYPE = 'text/html'
PDF_CONTENT_TYPE = 'application/pdf'

FILE_MIME_MAPPING = {
    '.pdf': PDF_CONTENT_TYPE,
}


class EmailTemplate(TemplateMessage):
    EMAIL = 'email'
    TYPE_CHOICES = (
        (EMAIL, _("Email")),
    )

    type = models.CharField(
        max_length=8,
        choices=TYPE_CHOICES,
        default=EMAIL,
        verbose_name=_("Type")
    )

    company = models.ForeignKey(
        'core.Company',
        verbose_name=_("Master company"),
        on_delete=models.CASCADE,
        related_name='email_templates',
        null=True,
        blank=True,
    )
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Template language"),
        on_delete=models.CASCADE,
        related_name='email_templates',
    )

    class Meta:
        verbose_name = _("E-mail Template")
        verbose_name_plural = _("E-mail Templates")
        ordering = ['name']
        unique_together = [
            'company',
            'name',
            'slug',
            'language',
        ]

    def __str__(self):
        return f'{self.name}'

class DefaultEmailTemplate(DefaultTemplateABS):
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Language"),
        on_delete=models.PROTECT,
        related_name='default_email_templates',
        db_index=True,
    )

    subject_template = models.CharField(
        max_length=256,
        default="",
        verbose_name=_("Subject template"),
        blank=True
    )

    message_html_template = models.TextField(
        default="",
        verbose_name=_("HTML template"),
        blank=True
    )

    class Meta:
        verbose_name = _("Default Email Template")
        verbose_name_plural = _("Default Email Templates")
        unique_together = (('slug', 'language'),)
        ordering = ['name']

    def save(self, *args, **kwargs):
        from r3sourcer.apps.core.models import Company
        super().save(*args, **kwargs)

        EmailTemplate.objects.\
            filter(slug=self.slug, language_id=self.language.alpha_2).\
            update(message_html_template=self.message_html_template,
                   message_text_template=self.message_text_template,
                   subject_template=self.subject_template)

        templates = []
        companies = Company.objects.filter(type=Company.COMPANY_TYPES.master,
                                           languages__language=self.language)
        for company in companies:
            if not EmailTemplate.objects.filter(company=company,
                                                slug=self.slug,
                                                language=self.language):
                obj = EmailTemplate(
                    name=self.name,
                    slug=self.slug,
                    message_html_template=self.message_html_template,
                    reply_timeout=self.reply_timeout,
                    delivery_timeout=self.delivery_timeout,
                    language_id=self.language.alpha_2,
                    company_id=company.id,
                    subject_template=self.subject_template
                )
                templates.append(obj)
        EmailTemplate.objects.bulk_create(templates)


class EmailMessage(TimeZoneUUIDModel):

    STATE_CHOICES = Choices(
        ('CREATED', _("Created")),
        ('WAIT', _("Waiting")),
        ('SENDING', _("Sending")),
        ('SENT', _("Sent")),
        ('ERROR', _("Error"))
    )

    state = models.CharField(
        default=STATE_CHOICES.CREATED,
        choices=STATE_CHOICES,
        max_length=16,
        verbose_name=_("State sending")
    )

    message_id = models.CharField(
        max_length=256,
        verbose_name=_("Email message id")
    )

    received_at = models.DateTimeField(
        verbose_name=_("When mail received"),
        null=True,
        blank=True
    )

    sent_at = models.DateTimeField(
        verbose_name=_("When mail sent"),
        null=True,
        blank=True
    )

    sender_email = models.CharField(
        max_length=512,
        default="",
        verbose_name=_("Sender email")
    )

    from_email = models.CharField(
        max_length=512,
        default="",
        verbose_name=_("From email")
    )

    subject = models.TextField(
        verbose_name=_("Mail subject")
    )

    headers = models.TextField(
        default="",
        verbose_name=_("Headers")
    )

    to_addresses = models.CharField(
        max_length=1024,
        default="",
        blank=True,
        verbose_name=_("Recipients")
    )

    is_read = models.BooleanField(
        default=False,
        verbose_name=_("Seen")
    )

    is_answered = models.BooleanField(
        default=False,
        verbose_name=_("Answered")
    )

    is_draft = models.BooleanField(
        default=True,
        verbose_name=_("Draft")
    )

    deleted = models.BooleanField(
        default=False,
        verbose_name=_("Deleted")
    )

    template = models.ForeignKey(
        EmailTemplate,
        verbose_name=_("Template"),
        default=None,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    # error info
    error_code = models.TextField(
        verbose_name=_("Error code"),
        default="",
        null=True,
        blank=True,
    )
    error_message = models.TextField(
        verbose_name=_("Error message"),
        default="",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("E-mail message")
        verbose_name_plural = _("E-mail messages")

    def __str__(self):
        return 'To {} from {}'.format(self.to_addresses.split(',')[0], self.from_email)

    def has_text_message(self):
        """ Check exists palin TEXT body """
        return self.bodies.filter(type=TEXT_CONTENT_TYPE).exists()

    def has_html_message(self):
        """ Check exists HTML body """
        return self.bodies.filter(type=HTML_CONTENT_TYPE).exists()

    def get_text_body(self):
        """ Return TEXT-body or None """
        try:
            return self.bodies.get(type=TEXT_CONTENT_TYPE).content
        except EmailBody.DoesNotExist:
            return None

    def get_html_body(self):
        """ Return HTML-body or None """
        try:
            return self.bodies.get(type=HTML_CONTENT_TYPE).content
        except EmailBody.DoesNotExist:
            return None

    @classmethod
    def owned_by_lookups(cls, owner):
        from r3sourcer.apps.core.models import Company
        if isinstance(owner, Company):
            return [models.Q(template__company=owner)]


class EmailBody(UUIDModel, models.Model):
    """ Mail message body """

    UUID_PATTERN = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

    content_id = models.IntegerField(
        default=None,
        null=True,
        verbose_name=_("Content id")
    )

    section = models.CharField(
        default="1",
        max_length=8,
        verbose_name=_("Section")
    )

    content = models.TextField(
        verbose_name=_("Mail message body"),
        blank=True,
        null=True
    )

    encoding = models.CharField(
        max_length=32,
        default="",
        verbose_name=_("Encoding")
    )

    mime = models.TextField(
        default="",
        verbose_name=_("Mime")
    )

    message_mime = models.TextField(
        default="",
        verbose_name=_("Message mime")
    )

    size = models.IntegerField(
        default=0,
        verbose_name=_("Size")
    )

    type = models.CharField(
        max_length=32,
        default=TEXT_CONTENT_TYPE,
        verbose_name=_("Type")
    )

    message = models.ForeignKey(
        EmailMessage,
        related_name='bodies',
        verbose_name=_("Email message"),
        on_delete=models.PROTECT
    )

    file = models.ForeignKey(
        File,
        related_name='bodies',
        verbose_name=_('File'),
        on_delete=models.CASCADE,
        null=True
    )

    class Meta:
        verbose_name = _("Body of E-mail message")
        verbose_name_plural = _("Bodies of E-mail messages")

    def __str__(self):
        return 'Message: {}'.format(self.message.message_id)

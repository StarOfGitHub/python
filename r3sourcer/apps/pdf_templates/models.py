from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.template import Context, Template

from r3sourcer.helpers.models.abs import UUIDModel


class PDFTemplateAbstract(UUIDModel):

    name = models.CharField(
        max_length=256,
        default="",
        verbose_name=_("Template Name"),
    )

    slug = models.SlugField()

    html_template = models.TextField(
        default="",
        verbose_name=_("HTML template"),
        blank=True
    )

    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Language"),
        on_delete=models.PROTECT,
        related_name='pdf_templates',
    )

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return f'{self.name} {self.language}'


class PDFTemplate(PDFTemplateAbstract):

    company = models.ForeignKey(
        'core.Company',
        verbose_name=_("Master company"),
        on_delete=models.CASCADE,
        related_name='pdf_templates',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("PDF Template")
        verbose_name_plural = _("PDF Templates")
        unique_together = [
            'company',
            'name',
            'slug',
            'language',
        ]

    def render(self, context):
        """
        Template rendering, variables substitution.
        """

        tpl = Template(self.html_template)
        return tpl.render(Context(context))


class DefaultPDFTemplate(PDFTemplateAbstract):

    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Language"),
        on_delete=models.PROTECT,
        related_name='pdf_default_templates',
    )

    class Meta:
        verbose_name = _("Default PDF Template")
        verbose_name_plural = _("Default PDF Templates")
        unique_together = [
            'name',
            'slug',
            'language',
        ]

    def save(self, *args, **kwargs):
        from r3sourcer.apps.core.models import Company
        super().save(*args, **kwargs)

        templates = []
        for company in Company.objects.filter(
                    type=Company.COMPANY_TYPES.master,
                    languages__language=self.language
                ).exclude(
                    pdf_templates__slug=self.slug,
                ):
            obj = PDFTemplate(
                name=self.name,
                slug=self.slug,
                html_template=self.html_template,
                language_id=self.language.alpha_2,
                company_id=company.id)
            templates.append(obj)
        PDFTemplate.objects.bulk_create(templates)

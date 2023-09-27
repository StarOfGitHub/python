from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django import forms
from django.forms import model_to_dict

from r3sourcer.apps.core.models import Language
from r3sourcer.apps.email_interface import models as email_models
from r3sourcer.helpers.admin.filters import LanguageListFilter, CompanyListFilter


class EmailTemplateAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ['name', 'company', 'slug', 'language_name']
    search_fields = ('name', 'company__short_name', 'slug')
    ordering = ['company', 'slug', 'language']
    list_filter = (CompanyListFilter, LanguageListFilter, 'name')

    @classmethod
    def language_name(cls, obj):
        return obj.language.name


class CreateWithLanguage(ActionForm):
    language_id = forms.ModelChoiceField(Language.objects.all(), required=False)


def create_with_languages(modeladmin, request, queryset):
    if not request.POST.get('language_id'):
        modeladmin.message_user(request, "Choose language", messages.ERROR)
        return
    for obj in queryset:
        src_template = model_to_dict(obj, exclude=['id', 'language'])
        unique = dict(slug=src_template['slug'],
                      language_id=request.POST['language_id'])
        qs = email_models.DefaultEmailTemplate.objects.filter(**unique)
        if qs.all():
            modeladmin.message_user(request,
                                    'Template with slug <{slug}> and language <{language_id}> already exists'
                                    .format(**unique),
                                    messages.ERROR)
            continue
        new_template = email_models.DefaultEmailTemplate(**src_template)
        new_template.language_id = request.POST['language_id']
        new_template.save()
        modeladmin.message_user(request,
                                "Template with slug <{slug}> and language <language_id> successfully copied"
                                .format(**unique),
                                messages.SUCCESS)


create_with_languages.short_description = 'Copy template with selected language'


class DefaultEmailTemplateAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ['name', 'slug', 'language_name']
    ordering = ['slug', 'language']
    list_filter = (LanguageListFilter, 'name')
    action_form = CreateWithLanguage
    actions = [create_with_languages]

    @classmethod
    def language_name(cls, obj):
        return obj.language.name


admin.site.register(
    email_models.EmailMessage,
    list_display=['from_email', 'to_addresses', 'template', 'created_at'],
    search_fields=['from_email', 'to_addresses', 'template__name']
)
admin.site.register(email_models.EmailBody, list_display=['message', 'created_at'])
admin.site.register(email_models.DefaultEmailTemplate, DefaultEmailTemplateAdmin)
admin.site.register(email_models.EmailTemplate, EmailTemplateAdmin)

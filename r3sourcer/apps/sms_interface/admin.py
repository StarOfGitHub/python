from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django import forms
from django.forms import model_to_dict

from . import models
from ..core.models import Language
from ...helpers.admin.filters import LanguageListFilter, CompanyListFilter


class SMSTemplateAdmin(admin.ModelAdmin):
    # prepopulated_fields = {"slug": ("name",)}
    list_display = ['name', 'company', 'slug', 'language_name']
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
        qs = models.DefaultSMSTemplate.objects.filter(**unique)
        if qs.all():
            modeladmin.message_user(request,
                                    'Template with slug <{slug}> and language <{language_id}> already exists'
                                    .format(**unique),
                                    messages.ERROR)
            continue
        new_template = models.DefaultSMSTemplate(**src_template)
        new_template.language_id = request.POST['language_id']
        new_template.save()
        modeladmin.message_user(request,
                                "Template with slug <{slug}> and language <language_id> successfully copied"
                                .format(**unique),
                                messages.SUCCESS)


create_with_languages.short_description = 'Copy template with selected language'


class DefaultSMSTemplateAdmin(admin.ModelAdmin):
    # prepopulated_fields = {"slug": ("name",)}
    list_display = ['name', 'slug', 'language_name']
    ordering = ['name', 'language']
    search_fields = ['name']
    list_filter = (LanguageListFilter, 'name')
    action_form = CreateWithLanguage
    actions = [create_with_languages]

    @classmethod
    def language_name(cls, obj):
        return obj.language.name


class SMSMessageAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'template', 'sent_at', 'company', 'related_content_type', 'text']


admin.site.register(models.SMSMessage, SMSMessageAdmin)
admin.site.register(models.SMSRelatedObject)
admin.site.register(models.SMSTemplate, SMSTemplateAdmin)
admin.site.register(models.DefaultSMSTemplate, DefaultSMSTemplateAdmin)

from django.contrib import admin

from .core import BaseAdminPermissionMixin
from ..models import CompanyLanguage


class CompanyLanguageAdmin(BaseAdminPermissionMixin, admin.ModelAdmin):

    list_display = ('company', 'language_name')
    search_fields = ('company', 'language_name')

    @classmethod
    def language_name(cls, obj):
        return obj.language.name


admin.site.register(CompanyLanguage, CompanyLanguageAdmin)

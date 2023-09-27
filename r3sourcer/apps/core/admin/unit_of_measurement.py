from django.contrib import admin

from .core import BaseAdminPermissionMixin
from ..models import UnitOfMeasurement, UOMLanguage


class UOMLanguageInline(admin.TabularInline):
    model = UOMLanguage
    extra = 0


class LanguageAdmin(BaseAdminPermissionMixin, admin.ModelAdmin):

    list_display = ('name', 'short_name', 'default')
    search_fields = ('name', 'short_name')
    inlines = [UOMLanguageInline]


admin.site.register(UnitOfMeasurement, LanguageAdmin)

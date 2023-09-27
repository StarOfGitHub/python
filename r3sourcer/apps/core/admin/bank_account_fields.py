from django.contrib import admin

from .core import BaseAdminPermissionMixin
from ..models import BankAccountField, BankAccountFieldLanguage


class BankAccountFieldLanguageInline(admin.TabularInline):
    model = BankAccountFieldLanguage


class BankAccountFieldAdmin(BaseAdminPermissionMixin, admin.ModelAdmin):

    list_display = ('name', 'description')
    search_fields = ('name',)
    inlines = (BankAccountFieldLanguageInline,)


admin.site.register(BankAccountField, BankAccountFieldAdmin)

from django.contrib import admin

from .core import BaseAdminPermissionMixin
from ..models import BankAccountLayout, BankAccountLayoutField, BankAccountLayoutCountry


class BankAccountFieldInline(admin.TabularInline):
    model = BankAccountLayoutField


class BankAccountCountryInline(admin.TabularInline):
    model = BankAccountLayoutCountry
    list_display = ('country_name',)
    raw_id_fields = ('country',)
    extra = 1

    @classmethod
    def country_name(cls, obj):
        return obj.country.name


class BankAccountLayoutAdmin(BaseAdminPermissionMixin, admin.ModelAdmin):

    list_display = ('slug', 'name', 'description')
    search_fields = ('name', 'slug')
    inlines = (BankAccountFieldInline, BankAccountCountryInline)


admin.site.register(BankAccountLayout, BankAccountLayoutAdmin)

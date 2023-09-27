from django.contrib import admin
from django.contrib.admin.sites import NotRegistered

from r3sourcer.apps.core import models
from r3sourcer.apps.core.admin import (
    BaseAdmin, UserAdmin, CompanyAdmin, SuperuserAdmin, ContactAdmin, WorkflowNodeAdmin, CompanyWorkflowNodeAdmin,
    AddressAdmin, CompanyContactAdmin,
)

from r3sourcer.apps.logger.admin import LoggerMixin


DEFAULT_MODELS_LIST = [
    models.BankAccount,
    models.WorkflowObject,
    models.CompanyLocalization,
    models.Note,
]

BASE_MODELS_LIST = [models.CompanyAddress,
                    models.CompanyContactAddress,
                    models.CompanyContactRelationship,
                    models.SiteCompany]

SUPERUSER_MODELS_LIST = [models.Workflow]

try:
    admin.site.unregister(DEFAULT_MODELS_LIST)
except NotRegistered:
    pass

try:
    admin.site.unregister(BASE_MODELS_LIST)
except NotRegistered:
    pass

try:
    admin.site.unregister(SUPERUSER_MODELS_LIST)
except NotRegistered:
    pass

try:
    admin.site.unregister([models.User, models.Company, models.Contact, models.WorkflowNode, models.CompanyWorkflowNode, models.Address, ])
except NotRegistered:
    pass


class LoggerAdmin(LoggerMixin, admin.ModelAdmin):
    pass


class LoggerBaseAdmin(LoggerMixin, BaseAdmin):
    pass


class UserLoggerAdmin(LoggerMixin, UserAdmin):
    pass


class CompanyLoggerAdmin(LoggerMixin, CompanyAdmin):
    pass


class ContactLoggerAdmin(LoggerMixin, ContactAdmin):
    pass


class AddressLoggerAdmin(LoggerMixin, AddressAdmin):
    pass


class WorkflowNodeLoggerAdmin(LoggerMixin, WorkflowNodeAdmin):
    pass


class CompanyWorkflowNodeLoggerAdmin(LoggerMixin, CompanyWorkflowNodeAdmin):
    pass


class SuperuserLoggerAdmin(LoggerMixin, SuperuserAdmin):
    pass


class CompanyContactLoggerAdmin(LoggerMixin, CompanyContactAdmin):
    pass


admin.site.register(models.User, UserLoggerAdmin)
admin.site.register(models.Address, AddressAdmin)
admin.site.register(models.Company, CompanyLoggerAdmin)
admin.site.register(models.Contact, ContactLoggerAdmin)
admin.site.register(models.CompanyContact, CompanyContactLoggerAdmin)
admin.site.register(models.WorkflowNode, WorkflowNodeLoggerAdmin)
admin.site.register(models.CompanyWorkflowNode, CompanyWorkflowNodeLoggerAdmin)
admin.site.register(DEFAULT_MODELS_LIST, LoggerAdmin)
admin.site.register(BASE_MODELS_LIST, LoggerBaseAdmin)
admin.site.register(SUPERUSER_MODELS_LIST, SuperuserLoggerAdmin)

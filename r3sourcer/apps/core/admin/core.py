from django.conf import settings
from django.conf.urls import url
from django.contrib import admin, messages
from django.contrib.admin.options import csrf_protect_m
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.sites.models import Site
from django.forms import Textarea
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import ugettext_lazy as _
import nested_admin
import stripe
from functools import reduce

from r3sourcer.apps.billing.models import StripeCountryAccount as sca

from r3sourcer.apps.core_utils.filters import RelatedDropDownFilter
from r3sourcer.apps.core_utils.mixins import ExtendedDraggableMPTTAdmin
from r3sourcer.apps.billing.models import Subscription

from .. import forms
from .. import models
from ..utils.companies import get_closest_companies


class BaseAdminPermissionMixin(object):
    def get_queryset(self, request):
        qs = super(BaseAdminPermissionMixin, self).get_queryset(request)

        if not request.user.is_superuser:
            master_companies = get_closest_companies(request)
            if len(master_companies) > 0:
                lookups = []
                for master_company in master_companies:
                    regular_companies = master_company.get_regular_companies()
                    for rc in regular_companies:
                        temp = self.model.get_master_company_lookup(rc)
                        if temp:
                            lookups.append(temp)

                    temp = self.model.get_master_company_lookup(master_company)
                    if temp:
                        lookups.append(temp)

                if lookups:
                    from operator import __or__ as OR
                    return qs.filter(reduce(OR, lookups)).distinct()
                else:
                    return qs.none()
            else:
                return qs.none()
        return qs


class ContactInlineAdmin(admin.TabularInline):

    verbose_name_plural = _("Contact information")
    form = forms.ContactForm
    model = models.Contact
    extra = 0
    min_num = 1
    max_num = 1


class UserAdmin(BaseUserAdmin):

    change_form_template = 'loginas/change_form.html'

    filter_horizontal = ('groups', 'role')

    fieldsets = (
        (_("Roles"), {
            'classes': ['collapse'],
            'fields': ['role']
        }),
        (_("Permissions"), {
            'classes': ['collapse'],
            'fields': ['is_active', ('is_staff', 'is_superuser'), 'groups', 'user_permissions']
        }),
        (_("Details"), {
            'classes': ['collapse'],
            'fields': ['date_joined', 'last_login']
        })
    )

    readonly_fields = ('date_joined', 'last_login')

    list_display = ('get_full_name', 'email', 'phone_mobile', 'is_active')
    list_display_links = list_display
    ordering = ('date_joined',)
    search_fields = ('contact__email', 'contact__phone_mobile', 'contact__first_name', 'contact__last_name')

    inlines = [ContactInlineAdmin]

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        if hasattr(self.model, 'created_by'):
            fields += ('created_by',)
        return fields

    def get_fieldsets(self, request, obj=None):
        fieldsets = self.fieldsets
        if hasattr(self.model, 'created_by'):
            fieldsets += ((None, {'fields': ['created_by']}),)
        if obj is None:
            return (
                (_("Password"), {
                    'fields': ['password1', 'password2']
                }),
            ) + fieldsets
        return (
            (_("Password"), {
                'fields': ['password']
            }),
        ) + fieldsets


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 0


class CompanyIndustryRel(admin.TabularInline):
    model = models.CompanyIndustryRel
    extra = 0


class ContactLanguageInlineAdmin(admin.TabularInline):
    model = models.ContactLanguage
    extra = 0


class ContactAdmin(admin.ModelAdmin):

    search_fields = ('email', 'phone_mobile', 'first_name', 'last_name',)
    inlines = [ContactLanguageInlineAdmin]


class CompanyContactAdmin(admin.ModelAdmin):
    search_fields = ('job_title', 'contact__first_name', 'contact__last_name')


class ContactAddressAdmin(admin.ModelAdmin):

    search_fields = ('contact__first_name', 'contact__last_name', 'contact__email', 'contact__phone_mobile')


class AddressAdmin(admin.ModelAdmin):

    search_fields = ('city__name', 'country__name', 'street_address', 'state__name',)
    list_display = ('__str__', 'country', 'city', 'state')


class CompanyAdmin(BaseAdminPermissionMixin, admin.ModelAdmin):

    list_display = ('name', 'get_industries', 'active_subscription')
    search_fields = ('name',)
    list_filter = ('type',)
    inlines = (SubscriptionInline, CompanyIndustryRel)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj:

            if obj.company_addresses.exists():
                company_address = obj.company_addresses.filter(hq=True).first()
                country = company_address.address.country
                fields_data = models.CompanyLocalization.get_company_metadata(country=country)

                for key, value in fields_data.items():
                    if key in form.base_fields:
                        if not value["active"]:
                            del form.base_fields[key]
                            continue

                        form.base_fields[key].label = value["verbose_value"]
                        form.base_fields[key].help_text = value["help_text"]
        return form

    def get_industries(self, obj):
        return ", ".join([str(p) for p in obj.industries.all()])

    def active_subscription(self, obj):
        return obj.active_subscription


class BaseAdmin(BaseAdminPermissionMixin, admin.ModelAdmin):
    pass


class MessageTemplateAdmin(admin.ModelAdmin):
    change_form_template = 'admin/message_templates/change_form.html'
    text_area_attrs = {
        'rows': 20,
        'data-editor': True,
        'data-mode': getattr(settings, 'DJANGOCMS_SNIPPET_THEME', 'html'),
        'data-theme': getattr(settings, 'DJANGOCMS_SNIPPET_MODE', 'github'),
    }

    formfield_overrides = {
        "message_html_template": {'widget': Textarea(attrs=text_area_attrs)}
    }

    def get_list_display(self, request):
        return [f.name for f in self.model._meta.fields if f.name != "id"] + ["get_clone"]

    def get_list_display_links(self, request, list_display):
        return ["name"]

    def get_clone(self, obj):
        return format_html(
            '<a href="{link}?{param_name}={param_value}">{name}</a>',
            link=reverse('admin:{app}_{model}_add'.format(
                app=self.model._meta.app_label,
                model=self.model._meta.model_name,
            )),
            param_name='from',
            param_value=obj.id,
            name=_("Clone"))

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if request.GET.get('from', None):
            try:
                cloning_obj = self.model.objects.get(id=request.GET.get('from', None))
                for f in self.model._meta.fields:
                    if f.name not in ["id", "updated_at", "created_at"]:
                        form.base_fields[f.name].initial = getattr(cloning_obj, f.name)
            except Exception as e:
                pass
        return form


class SuperuserAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class TagLanguageInline(nested_admin.NestedTabularInline):
    model = models.TagLanguage
    extra = 0


class TagAdmin(nested_admin.NestedModelAdmin):
    inlines = [TagLanguageInline]
    search_fields = ('name',)

    def get_queryset(self, request):
        qs = models.Tag.objects.filter(owner=models.Tag.TAG_OWNER.system)
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


class TagCompanyAdmin(nested_admin.NestedModelAdmin):
    inlines = [TagLanguageInline]

    def get_queryset(self, request):
        qs = models.Tag.objects.filter(owner=models.Tag.TAG_OWNER.company)
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


class CompanyTagAdmin(admin.ModelAdmin):
    list_display = ('tag', 'company')

    def get_queryset(self, request):
        qs = models.CompanyTag.objects.filter(tag__owner=models.Tag.TAG_OWNER.company)
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


class ExtranetNavigationAdmin(ExtendedDraggableMPTTAdmin):
    pass


class SiteAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class PublicHolidayAdmin(admin.ModelAdmin):

    list_display = ('country', 'date', 'name')
    list_display_links = list_display

    change_list_template = "admin/publicholiday/change_list.html"
    list_filter = (('country', RelatedDropDownFilter),)

    def get_model_perms(self, request):
        # TODO: is supervisor perms
        return {
            'add': self.has_add_permission(request),
            'change': self.has_change_permission(request),
            'delete': self.has_delete_permission(request)
        }

    def changelist_view(self, request, extra_context=None):
        """ Extending context with holiday fetching form """

        extra_context = extra_context or {}
        extra_context['holiday_form'] = forms.PublicHolidayFetchingForm()
        return super(PublicHolidayAdmin, self).changelist_view(request, extra_context)

    def get_urls(self):
        """ Extending admin urls with custom view """

        urls = super(PublicHolidayAdmin, self).get_urls()
        return [url(r'^fetch-holiday-dates/$', self.admin_site.admin_view(self.fetch_public_holidays_view),
                    name='publicholiday_fetch_dates')] + urls

    @csrf_protect_m
    def fetch_public_holidays_view(self, request):
        """ Handler for holiday fetching """

        from r3sourcer.apps.core.tasks import fetch_holiday_dates
        form = forms.PublicHolidayFetchingForm(request.POST)
        if form.is_valid():
            country = form.cleaned_data['country']
            year = form.cleaned_data['year']
            month = form.cleaned_data['month']
            fetch_holiday_dates.apply_async(kwargs={'country_code': country.code3, 'year': year, 'month': month})
            self.message_user(request, _("Dates will be fetched"))
        else:
            self.message_user(request, _("Wrong form"), messages.ERROR)
        return redirect(reverse('admin:%s_%s_changelist' % (self.model._meta.app_label, self.model._meta.model_name)))


class WorkflowNodeAdmin(SuperuserAdmin):

    search_fields = ('name_before_activation', 'name_after_activation', 'workflow__name')
    list_display = ('workflow', 'name_before_activation', 'active',)


class CompanyWorkflowNodeAdmin(SuperuserAdmin):

    search_fields = ('company__name', 'workflow_node__workflow__name', 'workflow_node__name_before_activation',
                     'workflow_node__name_after_activation')
    list_display = ('company', 'workflow_node', 'active',)
    raw_id_fields = ('company', 'workflow_node')


class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'provider_company',
        'customer_company',
        'number',
        'order_number',
        'period',
        'separation_rule',
        'approved',
        'sync_status',
    )
    ordering = ('-date',)


class InvoiceRuleAdmin(SuperuserAdmin):
    list_display = (
        'company',
        'period',
        'separation_rule',
    )


class CompanyRelAdmin(SuperuserAdmin):
    list_display = (
        'master_company',
        'regular_company',
        #'primary_contact',
        #'manager',
    )


class CompanyAddressAdmin(admin.ModelAdmin):

    search_fields = ('company__name', 'name')
    list_display = ('__str__', 'company__name', 'active', 'hq')


class VATAdmin(admin.ModelAdmin):
    list_display = (
        'country',
        'name',
    )
    # exclude = ('stripe_id',)

    def save_model(self, request, obj, form, change):
        country_code2 = obj.country_id
        stripe.api_key = sca.get_stripe_key(country_code2)
        if not change:
            # create tax rate
            tax_obj = stripe.TaxRate.create(
                display_name=obj.name,
                description=obj.name,
                jurisdiction=obj.country,
                percentage=obj.stripe_rate,
                inclusive=False,
            )
            stripe_id = tax_obj.get('id')
            obj.stripe_id = stripe_id
        if change:
            # update tax rate (stripe does not allow to change rate on update)
            stripe.TaxRate.modify(
                obj.stripe_id,
                display_name=obj.name,
                description=obj.name,
                jurisdiction=obj.country,
            )
        super().save_model(request, obj, form, change)


class InvoiceLineAdmin(SuperuserAdmin):
    list_display = (
        'date',
        'invoice',
        'invoice_provider_company',
        'invoice_customer_company',
        'invoice_number',
        'invoice_order_number',
        'timesheet',
    )
    ordering = ('-invoice__number', '-date',)

    def invoice_provider_company(self, obj):
        return obj.invoice.provider_company

    def invoice_customer_company(self, obj):
        return obj.invoice.customer_company

    def invoice_number(self, obj):
        return obj.invoice.number

    def invoice_order_number(self, obj):
        return obj.invoice.order_number


if admin.site.is_registered(Site):
    admin.site.unregister(Site)


admin.site.site_header = "Core Administration"
admin.site.register(models.Contact, ContactAdmin)
admin.site.register(models.ContactAddress, ContactAddressAdmin)
admin.site.register(models.User, UserAdmin)
admin.site.register(models.BankAccount)
admin.site.register(models.ContactBankAccount)
admin.site.register(models.Company, CompanyAdmin)
admin.site.register(models.Address, AddressAdmin)
admin.site.register(models.CompanyRel, CompanyRelAdmin)
admin.site.register(models.CompanyAddress, CompanyAddressAdmin)
admin.site.register(models.CompanyLocalization)
admin.site.register(models.CompanyContactAddress, BaseAdmin)
admin.site.register(models.CompanyContactRelationship, BaseAdmin)
admin.site.register(models.Invoice, InvoiceAdmin)
admin.site.register(models.InvoiceLine, InvoiceLineAdmin)
admin.site.register(models.Tag, TagAdmin)
admin.site.register(models.TagCompany, TagCompanyAdmin)
admin.site.register(models.CompanyTag, CompanyTagAdmin)
admin.site.register(models.Note)
admin.site.register(models.Order)
admin.site.register(models.SiteCompany, BaseAdmin)
admin.site.register(models.VAT, VATAdmin)
admin.site.register(models.InvoiceRule, InvoiceRuleAdmin)
admin.site.register(models.ExtranetNavigation, ExtranetNavigationAdmin)
admin.site.register(models.Workflow)
admin.site.register(models.WorkflowNode, WorkflowNodeAdmin)
admin.site.register(models.WorkflowObject, SuperuserAdmin)
admin.site.register(models.CompanyWorkflowNode, CompanyWorkflowNodeAdmin)
admin.site.register(models.PublicHoliday, PublicHolidayAdmin)
admin.site.register(models.ContactUnavailability)
admin.site.register(models.CompanyIndustryRel)
admin.site.register(Site, SiteAdmin)
admin.site.register(models.Role)
admin.site.register(models.ContactRelationship)

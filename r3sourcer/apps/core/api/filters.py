from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.db.models.fields.related import ForeignObjectRel, OneToOneRel
from django_filters import CharFilter, UUIDFilter, NumberFilter, BooleanFilter, ModelChoiceFilter, ChoiceFilter
from django_filters.rest_framework import FilterSet
from rest_framework.filters import OrderingFilter

from r3sourcer.apps.core import models
from r3sourcer.apps.core_adapter.filters import DateRangeFilter, RangeNumberFilter
from r3sourcer.apps.core.utils.user import get_default_company
from r3sourcer.apps.core.utils.companies import get_site_master_company


class CompanyFilter(FilterSet):
    name = CharFilter(name='name', method='filter_name')
    country = CharFilter(name='addresses', method='filter_country')
    state = UUIDFilter(method='filter_state')
    status = NumberFilter(method='filter_status')
    portfolio_manager = UUIDFilter(method='filter_portfolio_manager')
    regular_company = UUIDFilter(method='filter_regular_company')
    current = BooleanFilter(method='filter_current')
    has_industry = BooleanFilter(method='filter_has_industry')
    approved_credit_limit = RangeNumberFilter()

    class Meta:
        model = models.Company
        fields = ['name', 'business_id', 'country', 'type', 'id', 'approved_credit_limit', 'credit_check']

    def filter_name(self, queryset, name, value):
        return queryset.filter(
            name__icontains=value,
        )

    def filter_country(self, queryset, name, value):
        return queryset.filter(
            company_addresses__hq=True,
            company_addresses__address__country=value
        )

    def filter_state(self, queryset, name, value):
        return queryset.filter(
            company_addresses__hq=True,
            company_addresses__address__state=value
        )

    def filter_status(self, queryset, name, value):
        objects = self._fetch_workflow_objects(value)
        return queryset.filter(
            Q(regular_companies__id__in=objects) |
            Q(master_companies__id__in=objects) |
            Q(master_companies__master_company__id=self.request.user.company.get_closest_master_company().id)
        ).distinct()

    def filter_regular_company(self, queryset, name, value):
        return queryset.filter(master_companies__regular_company=value)

    def filter_portfolio_manager(self, queryset, name, value):
        return queryset.filter(
            regular_companies__manager=value
        ).distinct()

    def _fetch_workflow_objects(self, value):  # pragma: no cover
        content_type = ContentType.objects.get_for_model(models.CompanyRel)
        exclude_values = models.WorkflowObject.objects.filter(
            state__number__gt=value, state__workflow__model=content_type, active=True
        ).values_list('object_id', flat=True)

        return models.WorkflowObject.objects.filter(
            state__number=value, state__workflow__model=content_type, active=True,
        ).exclude(
            object_id__in=set(exclude_values)
        ).distinct('object_id').values_list('object_id', flat=True)

    def filter_current(self, queryset, name, value):
        if value:
            company = get_site_master_company() or get_default_company()
            return queryset.filter(id=company.id)
        return queryset

    def filter_has_industry(self, queryset, name, value):
        if value:
            return queryset.filter(industries__isnull=False).distinct()
        return queryset


class CompanyLocalizationFilter(FilterSet):
    field_name = CharFilter(name='field_name', lookup_expr='icontains')
    country = CharFilter(name='country', method='filter_country')

    class Meta:
        model = models.CompanyLocalization
        fields = ['field_name', 'country']

    def filter_country(self, queryset, name, value):
        qs = queryset.filter(
            country=value
        )

        if qs.exists():
            return qs
        return queryset.filter(country__isnull=True)


class CompanyAddressFilter(FilterSet):
    portfolio_manager = UUIDFilter(method='filter_portfolio_manager')
    updated_at = DateRangeFilter()

    class Meta:
        model = models.CompanyAddress
        fields = ['portfolio_manager', 'company', 'primary_contact', 'updated_at']

    def filter_portfolio_manager(self, queryset, name, value):
        return queryset.filter(
            Q(company__regular_companies__manager=value) |
            Q(company__master_companies__manager=value)
        )


class ApiOrderingFilter(OrderingFilter):

    def is_valid_field(self, model, field):
        components = field.split('.', 1)
        if len(components) < 2:
            return False

        try:
            field = model._meta.get_field(components[0])

            if isinstance(field, OneToOneRel):
                return self.is_valid_field(field.related_model, components[1])

            if isinstance(field, ForeignObjectRel):
                return self.is_valid_field(field.model, components[1])

            if field.remote_field:
                return self.is_valid_field(field.related_model, components[1])

            return True
        except FieldDoesNotExist:
            return False

    def remove_invalid_fields(self, queryset, fields, view, request):
        res = [term.replace('.', '__') for term in fields if self.is_valid_field(queryset.model, term.lstrip('-'))]
        return res


class WorkflowNodeFilter(FilterSet):
    company = ModelChoiceFilter(queryset=models.Company.objects, method='filter_company')
    system = BooleanFilter(method='filter_system')
    workflow = UUIDFilter(method='filter_workflow')
    content_type = CharFilter(method='filter_content_type')
    hardlock = BooleanFilter(method='filter_hardlock', field_name='hardlock')

    _company = None
    _workflow = None

    class Meta:
        model = models.WorkflowNode
        fields = ['workflow', 'workflow__model', 'parent', 'number']

    def filter_workflow(self, queryset, name, value):
        self._workflow = value

        return queryset.filter(workflow=value)

    def filter_company(self, queryset, name, value):
        if not value:
            return queryset

        self._company = value

        return queryset.filter(
            company_workflow_nodes__company=value, company_workflow_nodes__active=True,
            active=True, parent__isnull=True
        ).distinct('id')

    def filter_system(self, queryset, name, value):
        if not value:
            return queryset

        workflow_qry = Q(workflow=self._workflow) if self._workflow else Q()
        site_company = get_site_master_company()
        system_nodes = models.WorkflowNode.objects.filter(
            workflow_qry, company_workflow_nodes__company=site_company, active=True
        ).distinct()

        if self._company:
            system_nodes_exclude = models.WorkflowNode.objects.filter(
                company_workflow_nodes__company=self._company,
                company_workflow_nodes__active=True
            ).values_list('id', flat=True)
            system_nodes = models.WorkflowNode.objects.filter(
                Q(company_workflow_nodes__company=self._company, active=True) |
                Q(id__in=system_nodes.values_list('id', flat=True)),
                workflow_qry
            ).exclude(id__in=system_nodes_exclude).distinct()

        return system_nodes

    def filter_content_type(self, queryset, name, value):
        try:
            app_label, model = value.split('.')
            content_type = ContentType.objects.get_by_natural_key(app_label, model.lower())

            self._workflow = models.Workflow.objects.get(model=content_type)
        except Exception:
            return queryset.none()

        return queryset.filter(workflow=self._workflow)

    def filter_hardlock(self, queryset, name, value):
        if value:
            return queryset.filter(hardlock=True)
        return queryset.filter(hardlock=False)


class CompanyWorkflowNodeFilter(FilterSet):

    only_parent = BooleanFilter(method='filter_only_parent')

    class Meta:
        model = models.CompanyWorkflowNode
        fields = ['company', 'active', 'workflow_node__workflow', 'workflow_node__parent']

    def filter_only_parent(self, queryset, name, value):
        return queryset.filter(workflow_node__parent__isnull=value)


class DashboardModuleFilter(FilterSet):

    model = CharFilter(name='content_type', lookup_expr='model__icontains')
    app_label = CharFilter(name='content_type', lookup_expr='app_label__icontains')

    class Meta:
        model = models.DashboardModule
        fields = ('model', 'app_label', 'is_active')


class CompanyContactFilter(FilterSet):
    company = UUIDFilter(method='filter_company')
    primary_contact = UUIDFilter(method='filter_primary_contact')
    is_manager = BooleanFilter(method='filter_is_manager')
    jobsites = UUIDFilter(method='filter_jobsite')
    customer_company = UUIDFilter(method='filter_customer_company', distinct=True)
    master_company = CharFilter(method='filter_master_company', distinct=True)

    class Meta:
        model = models.CompanyContact
        fields = ['id', 'job_title']

    def filter_company(self, queryset, name, value):
        return queryset.filter(relationships__company_id=value, relationships__active=True)

    def filter_primary_contact(self, queryset, name, value):
        return queryset.filter(
            relationships__company__primary_contact_id=value
        )

    def filter_is_manager(self, queryset, name, value):
        return queryset.filter(
            companies__isnull=False,
        )

    def filter_jobsite(self, queryset, name, value):
        return queryset.filter(jobsites=value)

    def filter_customer_company(self, queryset, name, value):
        return queryset.filter(company_accounts__regular_company=value).distinct()

    def filter_master_company(self, queryset, name, value):
        if value == 'current':
            company = get_site_master_company() or get_default_company()
            value = company.id

        return queryset.filter(relationships__company_id=value, relationships__active=True).distinct()


class CompanyContactRelationshipFilter(FilterSet):
    company = UUIDFilter(method='filter_company')
    contact = UUIDFilter(method='filter_contact')

    class Meta:
        model = models.CompanyContactRelationship
        fields = ['company', 'active']

    def filter_company(self, queryset, name, value):
        return queryset.filter(company_id=value)

    def filter_contact(self, queryset, name, value):
        return queryset.filter(company_contact__contact_id=value)


class FormFieldFilter(FilterSet):

    class Meta:
        model = models.FormField
        fields = ('group', )


class WorkflowObjectFilter(FilterSet):

    class Meta:
        model = models.WorkflowObject
        fields = ('object_id', 'active', 'state__workflow__name')


class CountryFilter(FilterSet):
    company = UUIDFilter(method='filter_company')

    class Meta:
        model = models.Country
        fields = ('code2', 'company')

    def filter_company(self, queryset, name, value):
        company_counries = models.CompanyAddress.objects.filter(company_id=value).order_by('hq')
        countries = [ca.address.country.code2 for ca in company_counries]
        return queryset.filter(code2__in=countries)


class RegionFilter(FilterSet):

    country = CharFilter(method='filter_country')

    class Meta:
        model = models.Region
        fields = ('country',)

    def filter_country(self, queryset, name, value):
        return queryset.filter(Q(country__code2=value) if len(value) == 2 else Q(country_id=value))


class CityFilter(FilterSet):

    class Meta:
        model = models.City
        fields = ('country', 'region')


class ContactFilter(FilterSet):

    state = UUIDFilter(method='filter_state')
    contact_type = CharFilter(method='filter_contact_type')
    is_company_contact = BooleanFilter(method='filter_is_company_contact')
    is_candidate_contact = BooleanFilter(method='filter_is_candidate_contact')

    class Meta:
        model = models.Contact
        fields = [
            'state', 'is_company_contact', 'is_candidate_contact', 'phone_mobile_verified', 'email_verified',
            'is_available'
        ]

    def filter_state(self, queryset, name, value):
        return queryset.filter(address__state=value)

    def filter_contact_type(self, queryset, name, value):
        return queryset.filter(user__role__name=value).distinct()

    def filter_is_company_contact(self, queryset, name, value):
        return queryset.filter(company_contact__isnull=not value)

    def filter_is_candidate_contact(self, queryset, name, value):
        return queryset.filter(candidate_contacts__isnull=not value)


class ContactAddressFilter(FilterSet):
    contact = UUIDFilter(method='filter_contact')

    class Meta:
        model = models.ContactAddress
        fields = ['contact', 'is_active']

    def filter_contact(self, queryset, name, value):
        return queryset.filter(contact__id=value)


class TagFilter(FilterSet):
    exclude = UUIDFilter(method='exclude_by_candidate')
    skill = UUIDFilter(method='filter_skill')

    class Meta:
        model = models.Tag
        fields = ['exclude', 'confidential']

    def exclude_by_candidate(self, queryset, name, value):
        return queryset.filter(active=True).exclude(tag_rels__candidate_contact_id=value)

    def filter_skill(self, queryset, name, value):
        return queryset.filter(skills=value).distinct()


class InvoiceFilter(FilterSet):

    class Meta:
        model = models.Invoice
        fields = ['customer_company', 'date', ]


class InvoiceLineFilter(FilterSet):

    class Meta:
        model = models.InvoiceLine
        fields = ['invoice']


class InvoiceRuleFilter(FilterSet):

    class Meta:
        model = models.InvoiceRule
        fields = ['company']


class OrderFilter(FilterSet):

    class Meta:
        model = models.Order
        fields = ['provider_company']


class NoteFilter(FilterSet):

    class Meta:
        model = models.Note
        fields = ['object_id']


class ContactUnavailabilityFilter(FilterSet):

    class Meta:
        model = models.ContactUnavailability
        fields = ['contact']


class UserFilter(FilterSet):

    role = ChoiceFilter(choices=models.Role.ROLE_NAMES, method='filter_role')

    class Meta:
        model = models.User
        fields = ['role']

    def filter_role(self, queryset, name, value):
        return queryset.filter(role__name=value)


class PublicHolidayFilter(FilterSet):
    date = DateRangeFilter()

    class Meta:
        model = models.PublicHoliday
        fields = ['date']

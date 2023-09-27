from django.contrib.sites.models import Site
from django.contrib.contenttypes.models import ContentType
from r3sourcer.apps.core.api.router import router
from rest_framework.permissions import AllowAny

from r3sourcer.apps.core import models
from r3sourcer.apps.core.api import serializers, viewsets, filters
from r3sourcer.apps.core.api.endpoints import ApiEndpoint


class ContactEndpoint(ApiEndpoint):
    model = models.Contact
    base_viewset = viewsets.ContactViewset
    serializer = serializers.ContactSerializer
    filter_class = filters.ContactFilter
    search_fields = (
        'title',
        'first_name',
        'last_name',
        'address__city__search_names',
        'email',
        'phone_mobile',
    )


class ContactAddressEndpoint(ApiEndpoint):
    model = models.ContactAddress
    base_viewset = viewsets.ContactAddressViewset
    base_serializer = serializers.ContactAddressSerializer
    filter_class = filters.ContactAddressFilter
    search_fields = (
        'contact__title',
        'contact__first_name',
        'contact__last_name',
        'address__city__search_names',
        'is_active',
    )


class CompanyEndpoint(ApiEndpoint):
    model = models.Company
    base_viewset = viewsets.CompanyViewset
    serializer = serializers.CompanyListSerializer
    filter_class = filters.CompanyFilter

    search_fields = (
        'name', 'company_addresses__address__street_address', 'company_addresses__address__city__search_names',
        'notes', 'description'
    )


class CompanyContactEndpoint(ApiEndpoint):

    model = models.CompanyContact
    base_viewset = viewsets.CompanyContactViewset
    serializer = serializers.CompanyContactRenderSerializer
    filter_class = filters.CompanyContactFilter

    search_fields = ('job_title', 'contact__title', 'contact__first_name', 'contact__last_name')


class CompanyAddressEndpoint(ApiEndpoint):

    model = models.CompanyAddress
    base_viewset = viewsets.CompanyAddressViewset
    base_serializer = serializers.CompanyAddressSerializer
    filter_class = filters.CompanyAddressFilter


class CompanyContactRelationEndpoint(ApiEndpoint):

    model = models.CompanyContactRelationship
    serializer = serializers.CompanyContactRelationshipSerializer
    filter_class = filters.CompanyContactRelationshipFilter
    base_viewset = viewsets.CompanyContactRelationshipViewset


class CompanyRelEndpoint(ApiEndpoint):

    model = models.CompanyRel


class CompanyLocalizationEndpoint(ApiEndpoint):

    model = models.CompanyLocalization
    filter_class = filters.CompanyLocalizationFilter


class SiteEndpoint(ApiEndpoint):

    model = Site
    base_viewset = viewsets.SiteViewset


class NavigationEndpoint(ApiEndpoint):

    model = models.ExtranetNavigation
    base_viewset = viewsets.NavigationViewset
    serializer = serializers.NavigationSerializer


class WorkflowEndpoint(ApiEndpoint):

    model = models.Workflow
    search_fields = ('name', 'model__app_label', 'model__model', )


class WorkflowNodeEndpoint(ApiEndpoint):

    model = models.WorkflowNode
    base_viewset = viewsets.WorkflowNodeViewset
    serializer = serializers.WorkflowNodeSerializer
    filter_class = filters.WorkflowNodeFilter

    search_fields = ('name_before_activation', )


class CompanyWorkflowNodeEndpoint(ApiEndpoint):

    model = models.CompanyWorkflowNode
    base_viewset = viewsets.CompanyWorkflowNodeViewset
    filter_class = filters.CompanyWorkflowNodeFilter
    serializer = serializers.CompanyWorkflowNodeSerializer

    search_fields = ('workflow_node__name_before_activation', )


class WorkflowObjectEndpoint(ApiEndpoint):

    model = models.WorkflowObject
    serializer = serializers.WorkflowObjectSerializer
    filter_class = filters.WorkflowObjectFilter


class DashboardModuleEndpoint(ApiEndpoint):

    model = models.DashboardModule
    base_viewset = viewsets.DashboardModuleViewSet
    filter_class = filters.DashboardModuleFilter
    serializer = serializers.DashboardModuleSerializer


class UserDashboardModuleEndpoint(ApiEndpoint):

    model = models.UserDashboardModule
    base_viewset = viewsets.UserDashboardModuleViewSet
    serializer = serializers.UserDashboardModuleSerializer


class BaseFormFieldEndpoint(ApiEndpoint):

    filter_class = filters.FormFieldFilter

    def get_fieldsets(self):
        return self.model.get_serializer_fields()


class CheckBoxFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.CheckBoxFormField
    serializer = serializers.CheckBoxFormFieldSerializer


class ImageFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.ImageFormField
    serializer = serializers.ImageFormFieldSerializer


class RadioButtonsFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.RadioButtonsFormField
    serializer = serializers.RadioButtonsFormFieldSerializer


class TextAreaFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.TextAreaFormField
    serializer = serializers.TextAreaFormFieldSerializer


class TextFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.TextFormField
    serializer = serializers.TextFormFieldSerializer


class SelectFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.SelectFormField
    serializer = serializers.SelectFormFieldSerializer


class DateFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.DateFormField
    serializer = serializers.DateFormFieldSerializer


class NumberFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.NumberFormField
    serializer = serializers.NumberFormFieldSerializer


class ModelFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.ModelFormField
    serializer = serializers.ModelFormFieldSerializer


class FileFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.FileFormField
    serializer = serializers.FileFormFieldSerializer


class RelatedFormFieldEndpoint(BaseFormFieldEndpoint):

    model = models.RelatedFormField
    serializer = serializers.RelatedFormFieldSerializer


class FormFieldGroupEndpoint(ApiEndpoint):

    model = models.FormFieldGroup
    base_serializer = serializers.FormFieldGroupSerializer


class FormEndpoint(ApiEndpoint):
    model = models.Form
    base_viewset = viewsets.FormViewSet


class FormBuilderEndpoint(ApiEndpoint):

    model = models.FormBuilder
    base_viewset = viewsets.FormBuilderViewSet


class ContentTypeEndpoint(ApiEndpoint):

    model = ContentType
    base_viewset = viewsets.ContentTypeViewSet
    search_fields = ('model', )


class CountryEndpoint(ApiEndpoint):

    model = models.Country
    base_viewset = viewsets.CitiesLightViewSet
    filter_class = filters.CountryFilter
    search_fields = ('name', 'alternate_names')


class RegionEndpoint(ApiEndpoint):

    model = models.Region
    base_viewset = viewsets.CitiesLightViewSet
    filter_class = filters.RegionFilter
    search_fields = ('name', 'alternate_names')


class CityEndpoint(ApiEndpoint):

    model = models.City
    base_viewset = viewsets.CitiesLightViewSet
    filter_class = filters.CityFilter
    search_fields = ('name', 'alternate_names')


class InvoiceEndpoint(ApiEndpoint):
    model = models.Invoice
    serializer = serializers.InvoiceLineSerializer
    filter_class = filters.InvoiceFilter


class InvoiceLineEndpoint(ApiEndpoint):

    model = models.InvoiceLine
    serializer = serializers.InvoiceLineSerializer
    filter_class = filters.InvoiceLineFilter


class InvoiceRuleEndpoint(ApiEndpoint):

    model = models.InvoiceRule
    serializer = serializers.InvoiceRuleSerializer
    filter_class = filters.InvoiceRuleFilter


class OrderEndpoint(ApiEndpoint):

    model = models.Order
    filter_class = filters.OrderFilter


class NoteEndpoint(ApiEndpoint):

    model = models.Note
    serializer = serializers.NoteSerializer
    filter_class = filters.NoteFilter
    # base_viewset = viewsets.NoteViewset


class NoteFileEndpoint(ApiEndpoint):

    model = models.NoteFile
    serializer = serializers.NoteFileSerializer


class ContactUnavailabilityEndpoint(ApiEndpoint):

    model = models.ContactUnavailability
    filter_class = filters.ContactUnavailabilityFilter


class BankAccountEndpoint(ApiEndpoint):

    model = models.BankAccount
    search_fields = ('bank_name', 'bank_account_name')


class UserEndpoint(ApiEndpoint):

    model = models.User
    filter_class = filters.UserFilter
    serializer_fields = (
        'id', 'date_joined', {
            'contact': ('id', 'email', 'phone_mobile'),
        }
    )
    search_fields = ('contact__first_name', 'contact__last_name', 'contact__email', 'contact__phone_mobile')


class AddressEndpoint(ApiEndpoint):

    model = models.Address
    serializer = serializers.AddressSerializer
    base_viewset = viewsets.AddressViewset
    permission_classes = [AllowAny]


class TagEndpoint(ApiEndpoint):

    model = models.Tag
    filter_class = filters.TagFilter
    base_viewset = viewsets.TagViewSet
    serializer = serializers.TagSerializer
    search_fields = ('name', )
    serializer_fields = ('id', 'name', 'parent', 'active', 'evidence_required_for_approval', 'confidential')


class UomEndpoint(ApiEndpoint):

    model = models.UnitOfMeasurement
    serializer = serializers.UomSerializer


class PublicHolidayEndpoint(ApiEndpoint):

    base_viewset = viewsets.PublicHolidayViewset
    model = models.PublicHoliday
    serializer = serializers.PublicHolidaySerializer
    filter_class = filters.PublicHolidayFilter


router.register(endpoint=DashboardModuleEndpoint())
router.register(endpoint=UserDashboardModuleEndpoint())
router.register(endpoint=AddressEndpoint())
router.register(endpoint=BankAccountEndpoint())
router.register(endpoint=CityEndpoint())
router.register(endpoint=CompanyEndpoint())
router.register(endpoint=CompanyAddressEndpoint())
router.register(endpoint=CompanyContactEndpoint())
router.register(endpoint=CompanyContactRelationEndpoint())
router.register(endpoint=CompanyLocalizationEndpoint())
router.register(endpoint=CompanyRelEndpoint())
router.register(models.CompanyTradeReference)
router.register(endpoint=ContactEndpoint())
router.register(endpoint=ContactAddressEndpoint())
router.register(endpoint=ContactUnavailabilityEndpoint())
router.register(endpoint=CountryEndpoint())
router.register(models.FileStorage)
router.register(endpoint=InvoiceEndpoint())
router.register(endpoint=InvoiceLineEndpoint())
router.register(endpoint=NavigationEndpoint())
router.register(endpoint=NoteEndpoint())
router.register(endpoint=NoteFileEndpoint())
router.register(endpoint=OrderEndpoint())
router.register(endpoint=RegionEndpoint())
router.register(endpoint=TagEndpoint())
router.register(endpoint=SiteEndpoint())
router.register(endpoint=WorkflowEndpoint())
router.register(endpoint=WorkflowNodeEndpoint())
router.register(endpoint=CompanyWorkflowNodeEndpoint())
router.register(endpoint=WorkflowObjectEndpoint())
router.register(endpoint=FormBuilderEndpoint())
router.register(models.FormField, serializer=serializers.FormFieldSerializer)
router.register(endpoint=FormFieldGroupEndpoint())
router.register(endpoint=FormEndpoint())
router.register(endpoint=ImageFormFieldEndpoint())
router.register(endpoint=TextAreaFormFieldEndpoint())
router.register(endpoint=RadioButtonsFormFieldEndpoint())
router.register(endpoint=TextFormFieldEndpoint())
router.register(endpoint=SelectFormFieldEndpoint())
router.register(endpoint=DateFormFieldEndpoint())
router.register(endpoint=NumberFormFieldEndpoint())
router.register(endpoint=ModelFormFieldEndpoint())
router.register(endpoint=FileFormFieldEndpoint())
router.register(endpoint=CheckBoxFormFieldEndpoint())
router.register(endpoint=RelatedFormFieldEndpoint())
router.register(endpoint=ContentTypeEndpoint())
router.register(endpoint=InvoiceRuleEndpoint())
router.register(endpoint=UserEndpoint())
router.register(endpoint=UomEndpoint())
router.register(endpoint=PublicHolidayEndpoint())

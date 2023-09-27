import mock
import pytest

from r3sourcer.apps.core.api.filters import (
    CompanyFilter, CompanyLocalizationFilter, ApiOrderingFilter,
    CompanyAddressFilter, WorkflowNodeFilter
)
from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.core.api.serializers import ApiBaseModelSerializer
from r3sourcer.apps.core.api.viewsets import BaseApiViewset
from r3sourcer.apps.core.models import City, WorkflowNode

from django_mock_queries.query import create_model, MockSet, MockModel


ModelCompany = create_model('pk')
comp = ModelCompany(pk=1)
custom_comp = ModelCompany(pk=2)

workflownode_qs = MockSet(
    MockModel(id=1, number=1, active=True, parent=None, company_workflow_nodes=MockModel(company=comp, active=True)),
    MockModel(id=2, number=2, active=True, parent=None, company_workflow_nodes=MockModel(company=comp, active=True)),
    MockModel(id=3, number=2, active=True, parent=None,
              company_workflow_nodes=MockModel(company=custom_comp, active=True)),
)


@pytest.mark.django_db
class TestCountryFilters:

    def test_search_full_name_exists(self, company, rf):
        request = rf.get('/?name=Company')
        filter_obj = CompanyFilter(request=request)

        qs = filter_obj.filter_name(filter_obj.queryset, 'name', 'Company')

        assert qs.count() == 1
        assert qs.first() == company

    def test_search_partial_name_exists(self, company, rf):
        request = rf.get('/?name=Com')
        filter_obj = CompanyFilter(request=request)

        qs = filter_obj.filter_name(filter_obj.queryset, 'name', 'Com')

        assert qs.count() == 1
        assert qs.first() == company

    def test_search_case_insensative_name_exists(self, company, rf):
        request = rf.get('/?name=com')
        filter_obj = CompanyFilter(request=request)

        qs = filter_obj.filter_name(filter_obj.queryset, 'name', 'com')

        assert qs.count() == 1
        assert qs.first() == company

    def test_search_name_not_exists(self, company, rf):
        request = rf.get('/?name=com1')
        filter_obj = CompanyFilter(request=request)

        qs = filter_obj.filter_name(filter_obj.queryset, 'name', 'com1')

        assert qs.count() == 0

    def test_search_business_id_exists(self, company, rf):
        request = rf.get('/?business_id=111')
        filter_obj = CompanyFilter(request.GET, request=request)

        qs = filter_obj.qs

        assert qs.count() == 1
        assert qs.first() == company

    def test_search_business_id_not_exists(self, company, rf):
        request = rf.get('/?business_id=11')
        filter_obj = CompanyFilter(request.GET, request=request)

        qs = filter_obj.qs

        assert qs.count() == 0

    def test_search_for_country_exists(self, company_other, rf):
        request = rf.get('/?country=AU')
        filter_obj = CompanyFilter(request=request)

        qs = filter_obj.filter_country(filter_obj.queryset, 'name', 'AU')

        assert qs.count() == 1
        assert qs.first() == company_other

    def test_search_for_country_not_exists(self, company_other, rf):
        request = rf.get('/?country=GB')
        filter_obj = CompanyFilter(request=request)

        qs = filter_obj.filter_country(filter_obj.queryset, 'name', 'GB')

        assert qs.count() == 0


@pytest.mark.django_db
class TestCompanyLocalizationFilters:

    def test_get_by_country(self, company, rf):
        request = rf.get('/?country=AU')
        filter_obj = CompanyLocalizationFilter(request=request)

        qs = filter_obj.filter_country(filter_obj.queryset, 'country', 'AU')

        l10n = qs.filter(field_name='business_id').first()

        assert l10n is not None
        assert l10n.verbose_value == 'ABN'

    def test_get_by_country_default(self, company, rf):
        request = rf.get('/?country=TT')
        filter_obj = CompanyLocalizationFilter(request=request)

        qs = filter_obj.filter_country(filter_obj.queryset, 'country', 'TT')

        l10n = qs.filter(field_name='business_id').first()

        assert l10n is not None
        assert l10n.verbose_value == 'Company Number'


@pytest.mark.django_db
class TestCompanyAddressFilters:

    def test_filter_portfolio_manager(self, company, rf, company_address,
                                      primary_manager, company_rel):
        request = rf.get('/?portfolio_manager={}'.format(
            primary_manager.id
        ))
        filter_obj = CompanyAddressFilter(request=request)

        qs = filter_obj.filter_portfolio_manager(
            filter_obj.queryset, 'portfolio_manager',
            primary_manager.id
        )

        assert qs.count() == 1
        assert qs.first() == company_address

    def test_filter_portfolio_manager_not_exists(self, company, rf,
                                                 company_address,
                                                 primary_manager):
        request = rf.get('/?portfolio_manager={}'.format(
            primary_manager.id
        ))
        filter_obj = CompanyAddressFilter(request=request)

        qs = filter_obj.filter_portfolio_manager(
            filter_obj.queryset, 'portfolio_manager',
            primary_manager.id
        )

        assert qs.count() == 0


@pytest.mark.django_db
class TestApiOrderingFilter:

    def get_response_as_view(self, actions, request, viewset=None):
        kwargs = {'request': request}
        viewset = viewset
        view = viewset.as_view(actions)
        response = view(**kwargs)
        response.render()
        return response

    def test_get_default_valid_fields_with_endpoint(self):
        class CityEndpoint(ApiEndpoint):
            model = City
            fields = (
                'name',
                {
                    'country': ('name', ),
                }
            )

        order_filter = ApiOrderingFilter()
        endpoint = CityEndpoint()
        fields = order_filter.get_default_valid_fields(
            City.objects,
            endpoint.get_viewset()()
        )

        assert dict(fields).keys() == {'name', 'country', '__str__'}

    def test_get_default_valid_fields_without_endpoint(self):
        class CitySerializer(ApiBaseModelSerializer):
            class Meta:
                model = City
                fields = ('name', )

        class CityViewset(BaseApiViewset):
            queryset = City.objects.all()
            serializer_class = CitySerializer

        order_filter = ApiOrderingFilter()
        viewset = CityViewset()
        fields = order_filter.get_default_valid_fields(
            City.objects,
            viewset
        )

        assert dict(fields).keys() == {'name', '__str__'}

    def test_extended_ordering(self, rf):
        class CityEndpoint(ApiEndpoint):
            model = City
            fields = (
                'id', 'name',
                {
                    'country': ('name', 'code2'),
                }
            )

        view = CityEndpoint().get_viewset()
        request = rf.get('/', {'ordering': '-country.code2'})
        response = self.get_response_as_view({'get': 'list'}, request, viewset=view)
        assert len(response.data['results']) == 2
        assert response.data['results'][1]['name'] == 'Sydney'
        assert response.data['results'][0]['name'] == 'Kiev'


@pytest.mark.django_db
class TestWorkflowNodeFilter:

    def test_filter_company_none_value(self):
        filter_obj = WorkflowNodeFilter()

        res = filter_obj.filter_company(workflownode_qs, 'default', None)

        assert len(res) == 3

    @mock.patch('r3sourcer.apps.core.api.filters.get_default_company', return_value=comp)
    @mock.patch.object(WorkflowNode, 'get_company_nodes')
    def test_filter_company_default_company(self, mock_nodes, mock_default):
        mock_nodes.return_value = [10, 20]
        filter_obj = WorkflowNodeFilter()

        res = filter_obj.filter_company(workflownode_qs, 'default', comp)

        assert len(res) == 2

    @mock.patch('r3sourcer.apps.core.api.filters.get_default_company', return_value=comp)
    @mock.patch.object(WorkflowNode, 'get_company_nodes')
    def test_filter_company_not_default_company(self, mock_nodes, mock_default):
        mock_nodes.return_value = [10, 20]
        filter_obj = WorkflowNodeFilter()

        res = filter_obj.filter_company(
            workflownode_qs, 'default', custom_comp
        )

        assert len(res) == 1

import copy
import json

import mock
import pytest

from django.test.client import MULTIPART_CONTENT, BOUNDARY, encode_multipart
from guardian.shortcuts import assign_perm
from rest_framework import status, fields
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.test import force_authenticate

from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core import endpoints
from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.core.managers import AbstractObjectOwnerQuerySet
from r3sourcer.apps.core.models import Country, City, CompanyContact, DashboardModule, ExtranetNavigation
from r3sourcer.apps.core.service import FactoryService


class CountryEndpoint(ApiEndpoint):
    model = Country


class CityEndpoint(ApiEndpoint):
    model = City


CountryViewset = CountryEndpoint().get_viewset()
CityViewset = CityEndpoint().get_viewset()


@pytest.mark.django_db
class TestApiViewset:

    @pytest.fixture
    def actions(self):
        return {'get': 'list', 'post': 'create'}

    @pytest.fixture
    def actions_obj(self):
        return {'get': 'retrieve', 'put': 'update'}

    @pytest.fixture
    def viewset(self):
        return CityViewset()

    def get_response_as_view(self, actions, request, pk=None, viewset=None):
        kwargs = {'request': request}
        if pk is not None:
            kwargs['pk'] = pk
        viewset = viewset or CountryViewset
        view = viewset.as_view(actions)
        response = view(**kwargs)
        response.render()
        return response

    @mock.patch.object(CountryViewset, 'list')
    def test_error_response_format(self, mock_list, rf, actions):
        mock_list.side_effect = APIException

        req = rf.get('/')
        response = self.get_response_as_view(actions, req)

        assert 'status' in response.data
        assert 'errors' in response.data

    def test_list_all_fields_request(self, rf, actions):
        req = rf.get('/')
        response = self.get_response_as_view(actions, req)

        item = response.data['results'][0]
        assert set(item).issuperset({'id', 'name', 'code2'})

    def test_list_partial_fields_request(self, rf, actions):
        req = rf.get('/?fields=id&fields=name')
        response = self.get_response_as_view(actions, req)

        item = response.data['results'][0]
        assert set(item) == {'id', 'name'}

    def test_object_all_fields_request(self, rf, actions_obj, country):
        req = rf.get('/{}/'.format(country.id))
        response = self.get_response_as_view(actions_obj, req, pk=country.id)

        assert set(response.data).issuperset({'id', 'name', 'code2'})

    def test_object_partial_fields_request(self, rf, actions_obj, country):
        req = rf.get('/{}/?fields=id&fields=name'.format(country.id))
        response = self.get_response_as_view(actions_obj, req, pk=country.id)

        assert set(response.data) == {'id', 'name'}

    def test_list_show_related_object_request(self, rf, actions, country):
        req = rf.get('/cities')
        response = self.get_response_as_view(actions, req, viewset=CityViewset)

        item = response.data['results'][0]
        assert isinstance(item['country'], dict)
        assert 'name' in item['country']

    def test_object_show_related_object_request(self, rf, actions_obj, city):
        req = rf.get('/cities/{}/'.format(city.id))
        response = self.get_response_as_view(actions_obj, req, pk=city.id, viewset=CityViewset)

        item = response.data
        assert isinstance(item['country'], dict)
        assert 'name' in item['country']
        assert item['country']['name'] == 'Australia'

    def test_list_show_empty_related_object_request(self, rf, actions):
        req = rf.get('/cities/?related=')
        response = self.get_response_as_view(actions, req, viewset=CityViewset)

        item = response.data['results'][0]
        assert set(item['region']) == {'id', 'name', '__str__'}

    def test_list_show_direct_related_object_request(self, rf, actions):
        req = rf.get('/cities/?related=direct')
        response = self.get_response_as_view(actions, req, viewset=CityViewset)

        item = response.data['results'][0]
        assert 'country' in item['region']
        assert set(item['region']['country']) == {'id', 'name', '__str__'}

    def test_object_show_full_related_object_request(self, rf, actions_obj, city):
        req = rf.get('/cities/{}/?related=full'.format(city.id))
        response = self.get_response_as_view(actions_obj, req, pk=city.id, viewset=CityViewset)

        item = response.data
        assert 'country' in item['region']
        assert 'code2' in item['region']['country']

    def test_list_limit_query_param(self, rf, actions):
        req = rf.get('/cities/?limit=1')
        response = self.get_response_as_view(actions, req, viewset=CityViewset)

        assert len(response.data['results']) == 1

    def test_list_limit_zero_query_param(self, rf, actions):
        req = rf.get('/cities/?limit=')
        response = self.get_response_as_view(actions, req, viewset=CityViewset)

        assert len(response.data['results']) == City.objects.all().count()

    def test_list_limit_all_query_param(self, rf, actions):
        req = rf.get('/cities/?limit=-1')
        response = self.get_response_as_view(actions, req, viewset=CityViewset)

        assert len(response.data['results']) == City.objects.all().count()

    def test_list_without_pagination(self, rf, actions):
        req = rf.get('/cities/?limit=1')

        with mock.patch.object(CityViewset, 'pagination_class', new=None):
            response = self.get_response_as_view(actions, req, viewset=CityViewset)

            assert len(response.data) == City.objects.all().count()

    def test_http_method_names_without_options(self):
        with mock.patch.object(CityViewset, 'http_method_names', new=['get']):
            viewset = CityViewset()

            assert 'options' in viewset.http_method_names

    def test_clean_request_data_dict(self, viewset):
        data = {
            'id': 'id',
            'test': None,
        }
        res = viewset.clean_request_data(data)

        assert res.keys() == {'id'}

    def test_clean_request_data_list(self, viewset):
        data = [{
            'id': 'id',
            'test': None,
        }]
        res = viewset.clean_request_data(data)

        assert len(res) == 1
        assert res[0].keys() == {'id'}

    def test_prepare_internal_data_dict(self, viewset):
        data = {
            'id': 'id',
            'test': None,
            '__str__': 'str',
        }
        res = viewset._prepare_internal_data(data)

        assert res.keys() == {'id', 'test'}

    def test_prepare_internal_data_dict_with_empty(self, viewset):
        data = {
            'id': 'id',
            'test': fields.empty,
        }
        res = viewset._prepare_internal_data(data)

        assert res.keys() == {'id', 'test'}

    def test_prepare_internal_data_dict_with_empty_exclude(self, viewset):
        data = {
            'id': 'id',
            'test1': 'test',
            'test': fields.empty,
        }
        viewset.exclude_empty = True
        res = viewset._prepare_internal_data(data)
        viewset.exclude_empty = False

        assert res.keys() == {'id', 'test1'}

    def test_prepare_internal_data_dict_with_list(self, viewset):
        data = {
            'id': 'id',
            'test': [],
        }
        res = viewset._prepare_internal_data(data)

        assert res.keys() == {'id', 'test'}

    def test_prepare_internal_data_dict_only_id(self, viewset):
        data = {
            'id': 'id',
        }
        res = viewset._prepare_internal_data(data)

        assert res == 'id'

    def test_prepare_internal_data_list(self, viewset):
        data = [{
            'id': 'id',
            'test': 'test',
        }]
        res = viewset._prepare_internal_data(data)

        assert len(res) == 1
        assert res[0].keys() == {'id', 'test'}


class ResourceMixin:
    endpoint_class = None
    actions = {
        'get': 'retrieve',
        'put': 'update',
        'post': 'create',
        'delete': 'destroy',
    }

    def get_response_as_view(self, request, pk=None, endpoint=None, actions=None):
        kwargs = {'request': request, 'partial': request.method.lower() == 'put'}
        if pk is not None:
            kwargs['pk'] = pk
        endpoint = endpoint or self.endpoint_class
        viewset = endpoint().get_viewset()
        view = viewset.as_view(actions or self.actions)
        response = view(**kwargs)
        response.render()
        return response


@pytest.mark.django_db
class TestCompanyContactResource(ResourceMixin):
    endpoint_class = endpoints.CompanyContactEndpoint
    actions = {
        'post': 'create',
    }

    @pytest.fixture
    def company_contact_data(self, country):
        company_contact_data = {
            'title': 'Mr.',
            'first_name': 'Test',
            'last_name': 'Tester',
            'email': 'tester@test.tt',
            'phone_mobile': '+12345678940',
            'password': 'secret',
            'address': {
                'street_address': 'test str',
                'country': str(country.id),
            },
            'company': {
                'name': 'test com',
            }
        }
        return company_contact_data

    @pytest.fixture
    def company_contact_ref_data(self, company_contact_data, company):
        company_contact_data = copy.copy(company_contact_data)
        company_contact_data['company'] = str(company.id)
        return company_contact_data

    @mock.patch.object(FactoryService, 'get_instance')
    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address',
                return_value=(42, 42))
    def test_can_register_company_contact(self, mock_geo, mock_factory, rf,
                                          user,  company_contact_data):
        req = rf.post('/company_contacts/register/',
                      data=json.dumps(company_contact_data),
                      content_type='application/json')
        force_authenticate(req, user=user)

        response = self.get_response_as_view(req, actions={'post': 'register'})

        assert 'id' in response.data
        assert 201 == response.status_code
        assert CompanyContact.objects.filter(id=response.data['id']).exists()

    @mock.patch.object(FactoryService, 'get_instance')
    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address',
                return_value=(42, 42))
    def test_can_create_with_referenced_company(
            self, mock_geo, mock_factory, rf, user, company_contact_ref_data):
        req = rf.post('/company_contacts/register/',
                      data=json.dumps(company_contact_ref_data),
                      content_type='application/json')
        force_authenticate(req, user=user)

        response = self.get_response_as_view(req, actions={'post': 'register'})

        assert 'id' in response.data
        assert 201 == response.status_code
        assert CompanyContact.objects.filter(id=response.data['id']).exists()

    def get_company_contact_resource(self, rf, user=None):
        request = rf.get('/')
        request.user = user

        resource = endpoints.CompanyContactEndpoint().get_viewset()()
        resource.request = request
        resource.format_kwarg = None

        return resource

    def test_get_serializer_context(self, rf, staff_user):
        resource = self.get_company_contact_resource(rf)
        resource2 = self.get_company_contact_resource(rf, staff_user)

        context = resource.get_serializer_context()
        context2 = resource2.get_serializer_context()

        keys = {'approved_by_staff', 'approved_by_primary_contact'}
        assert keys.isdisjoint(context.keys())
        assert keys.issubset(context2.keys())
        assert isinstance(context2['approved_by_staff'], bool)
        assert isinstance(context2['approved_by_primary_contact'], bool)

    def test_is_approved_by_staff(self, staff_user, primary_user, staff_relationship, company_rel):
        resource = endpoints.CompanyContactEndpoint().get_viewset()()
        assert resource.is_approved_by_staff(staff_user)
        assert not resource.is_approved_by_staff(primary_user)

    def test_is_approved_by_manager(self, staff_user, primary_user, staff_relationship, company_rel):
        resource = endpoints.CompanyContactEndpoint().get_viewset()()
        assert not resource.is_approved_by_manager(staff_user)
        assert resource.is_approved_by_manager(primary_user)


@pytest.mark.django_db
class TestContactResource(ResourceMixin):
    endpoint_class = endpoints.ContactEndpoint
    actions = {
        'put': 'partial_update'
    }

    @pytest.fixture
    def contact_update_data(self, contact_data):
        keys = 'title first_name last_name email phone_mobile'.split()
        return {
            k: v
            for k, v in contact_data.items()
            if k in keys
        }

    @pytest.fixture
    def contact_picture_data(self, picture):
        return dict(picture=copy.deepcopy(picture), email='test_email@testemail.com')

    def test_can_update_contact(self, rf, contact, staff_user, contact_update_data):
        req = rf.put('/contacts/',
                     encode_multipart(BOUNDARY, contact_update_data),
                     content_type=MULTIPART_CONTENT)
        force_authenticate(req, user=staff_user)
        expected_data = contact_update_data.copy()
        expected_data['id'] = contact.id
        response = self.get_response_as_view(req, pk=contact.id)
        actual_data = {k: v for k, v in response.data.items() if k in expected_data}
        assert actual_data == expected_data
        assert response.status_code == 200

    def test_can_update_avatar(self, rf, contact, staff_user, contact_picture_data):
        req = rf.put('/contacts/',
                     encode_multipart(BOUNDARY, contact_picture_data),
                     content_type=MULTIPART_CONTENT)
        force_authenticate(req, user=staff_user)
        contact.picture = None
        contact.save()
        response = self.get_response_as_view(req, pk=contact.id)
        assert contact.picture is not None
        assert response.data.get('id', None) == contact.id
        assert response.data.get('picture', None) is not None
        assert response.status_code == 200

    def test_check_phone_valid(self, rf):
        req = rf.get('/contacts/validate?phone=%2B61234567891')

        resource = endpoints.ContactEndpoint().get_viewset()()
        response = resource.validate(req)

        assert response.data['status'] == 'success'
        assert response.data['data']['valid']

    def test_check_phone_invalid(self, rf):
        req = rf.get('/contacts/validate?phone=1234')

        resource = endpoints.ContactEndpoint().get_viewset()()
        with pytest.raises(ValidationError):
            resource.validate(req)

    def test_check_phone_empty(self, rf):
        req = rf.get('/contacts/validate?phone=')

        resource = endpoints.ContactEndpoint().get_viewset()()
        with pytest.raises(ValidationError):
            resource.validate(req)

    def test_check_email_valid(self, rf):
        req = rf.get('/contacts/validate?email=email@test.tt')

        resource = endpoints.ContactEndpoint().get_viewset()()
        response = resource.validate(req)

        assert response.data['status'] == 'success'
        assert response.data['data']['valid']

    def test_check_email_invalid(self, rf):
        req = rf.get('/contacts/validate?email=test')

        resource = endpoints.ContactEndpoint().get_viewset()()
        with pytest.raises(ValidationError):
            resource.validate(req)

    def test_check_email_empty(self, rf):
        req = rf.get('/contacts/validate?email=')

        resource = endpoints.ContactEndpoint().get_viewset()()
        with pytest.raises(ValidationError):
            resource.validate(req)

    def test_check_empty_validate(self, rf):
        req = rf.get('/contacts/validate')

        resource = endpoints.ContactEndpoint().get_viewset()()
        with pytest.raises(ValidationError):
            resource.validate(req)


@pytest.mark.django_db
class TestCompanyResource(ResourceMixin):
    endpoint_class = endpoints.CompanyEndpoint
    actions = {
        'put': 'partial_update'
    }

    @pytest.fixture
    def company_vs(self):
        return endpoints.CompanyEndpoint().get_viewset()

    def test_process_response_data_searching_country(self, rf, company_vs):
        req = rf.get('/company/?country=AU')

        resource = company_vs(request=req)
        data = {
            'count': 1,
        }

        resp_data = resource.process_response_data(data)

        assert 'message' in resp_data

    def test_process_response_data_searching_business_id(self, rf, company_vs):
        req = rf.get('/company/?business_id=1234')

        resource = company_vs(request=req)
        data = {
            'count': 1,
        }

        resp_data = resource.process_response_data(data)

        assert 'message' in resp_data

    def test_process_response_data_searching_without_pagination(self, rf, company_vs):
        req = rf.get('/company/?country=AU')

        resource = company_vs(request=req)
        data = [{
            'name': 'test'
        }]

        resp_data = resource.process_response_data(data)

        assert 'message' in resp_data

    def test_process_response_data_searching_not_found(self, rf, company_vs):
        req = rf.get('/company/?country=GB')

        resource = company_vs(request=req)
        data = {
            'count': 0,
        }

        resp_data = resource.process_response_data(data)

        assert 'data' not in resp_data

    def test_process_response_data_not_searching(self, rf, company_vs):
        req = rf.get('/company/')

        resource = company_vs(request=req)
        data = {
            'count': 1,
        }

        resp_data = resource.process_response_data(data)

        assert 'data' not in resp_data


@pytest.mark.django_db
class TestCompanyAddressViewset:

    @pytest.fixture
    def company_address_vs(self):
        return endpoints.CompanyAddressEndpoint().get_viewset()

    def test_get_queryset_no_site_company(self, rf, site, company_address_vs):
        req = rf.get('/')
        viewset = company_address_vs()
        company_address_vs.request = req

        qs = viewset.get_queryset()

        assert not qs.exists()

    def test_get_queryset_no_master_site_company(self, site, site_regular_company, rf, company_address_vs):
        req = rf.get('/')
        viewset = company_address_vs()
        company_address_vs.request = req

        qs = viewset.get_queryset()

        assert not qs.exists()

    def test_get_queryset_master_company(self, site, rf, site_company, company_address, company_address_vs):
        req = rf.get('/')
        viewset = company_address_vs()
        company_address_vs.request = req

        qs = viewset.get_queryset()

        assert qs.count() == 1
        assert qs.first() == company_address

    def test_get_queryset_regular_company(
        self, site, rf, site_company, company_address_regular, company_rel, company_address_vs
    ):
        req = rf.get('/')
        viewset = company_address_vs()
        company_address_vs.request = req

        qs = viewset.get_queryset()

        assert qs.count() == 1
        assert qs.first() == company_address_regular


@pytest.mark.django_db
class TestDashboardModules(ResourceMixin):
    endpoint_class = endpoints.DashboardModuleEndpoint
    actions = {
        'get': 'list',
        'post': 'create'
    }

    @pytest.fixture
    def assigned_modules(self, dashboard_modules, primary_manager):
        for m in dashboard_modules:
            assign_perm('can_use_module', primary_manager.contact.user, m)
        return dashboard_modules, primary_manager

    def test_get_all_modules(self, user, rf, dashboard_modules):
        req = rf.get('/core/dashboardmodules/')
        force_authenticate(req, user=user)
        resp_data = self.get_response_as_view(req)

        assert status.HTTP_200_OK == resp_data.status_code
        assert 'results' in resp_data.data
        assert len(resp_data.data['results']) == 0
        assert DashboardModule.objects.filter().exists()

    @mock.patch.object(AbstractObjectOwnerQuerySet, 'owned_by')
    def test_get_active_modules(self, mock_owned, rf, assigned_modules):
        modules, c_contact = assigned_modules
        mock_owned.return_value = DashboardModule.objects.all()
        req = rf.get('/core/dashboardmodules/?is_active=true')
        force_authenticate(req, user=c_contact.contact.user)
        resp_data = self.get_response_as_view(req)

        assert status.HTTP_200_OK == resp_data.status_code
        assert 'results' in resp_data.data
        assert len(resp_data.data['results']) == len([m for m in modules if m.is_active])

    @mock.patch.object(AbstractObjectOwnerQuerySet, 'owned_by')
    def test_get_inactive_modules(self, mock_owned, rf, assigned_modules):
        modules, c_contact = assigned_modules
        mock_owned.return_value = DashboardModule.objects.all()
        req = rf.get('/core/dashboardmodules/?is_active=false')
        force_authenticate(req, user=c_contact.contact.user)
        resp_data = self.get_response_as_view(req)

        assert status.HTTP_200_OK == resp_data.status_code
        assert 'results' in resp_data.data
        assert len(resp_data.data['results']) == len([m for m in modules if not m.is_active])

    @mock.patch.object(AbstractObjectOwnerQuerySet, 'owned_by')
    def test_get_module_filtering(self, mock_owned, rf, assigned_modules):
        modules, c_contact = assigned_modules
        mock_owned.return_value = DashboardModule.objects.all()
        req = rf.get('/core/dashboardmodules/?model=companycontact')
        force_authenticate(req, user=c_contact.contact.user)
        resp_data = self.get_response_as_view(req)

        assert status.HTTP_200_OK == resp_data.status_code
        assert 'results' in resp_data.data
        assert len(resp_data.data['results']) == 1

    def test_create_module(self, rf, assigned_modules):
        modules, c_contact = assigned_modules
        req = rf.post('/core/dashboardmodules/')
        force_authenticate(req, user=c_contact.contact.user)
        resp_data = self.get_response_as_view(req)

        assert status.HTTP_403_FORBIDDEN == resp_data.status_code
        assert 'errors' in resp_data.data


@pytest.mark.django_db
class TestUserDashboardModule(ResourceMixin):
    endpoint_class = endpoints.UserDashboardModuleEndpoint
    actions = {
        'get': 'list',
        'post': 'create'
    }

    def test_create_module_without_company_contact_relation(self, rf, user, dashboard_modules):
        req = rf.post('/core/userdashboardmodules/',
                      data=json.dumps({
                          'dashboard_module': str(dashboard_modules[0].id),
                          'position': 1
                      }),
                      content_type='application/json')
        force_authenticate(req, user=user)
        resp_data = self.get_response_as_view(req)

        assert resp_data.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'error' == resp_data.data['status']
        assert 'errors' in resp_data.data
        assert 'You should be CompanyContact to creating module' in resp_data.data['errors']['detail']


class TestNavigationViewset(ResourceMixin):
    endpoint_class = endpoints.NavigationEndpoint

    def test_navigation_retrieve_by_all_roles(self, rf, user):
        client_url = 'client_url'
        manager_url = 'manager_url'
        candidate_url = 'candidate_url'
        url = '/core/extranetnavigations/'

        ExtranetNavigation.objects.create(url=client_url,
                                          access_level=ExtranetNavigation.CLIENT)
        ExtranetNavigation.objects.create(url=manager_url,
                                          access_level=ExtranetNavigation.MANAGER)
        ExtranetNavigation.objects.create(url=candidate_url,
                                          access_level=ExtranetNavigation.CANDIDATE)
        company_contact = CompanyContact.objects.create(contact=user.contact, role=CompanyContact.MANAGER)
        request = rf.get(url)
        force_authenticate(request, user=user)
        response = self.get_response_as_view(request, actions={'get': 'list'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['url'] == manager_url

        company_contact.role = CompanyContact.CLIENT
        company_contact.save()
        request = rf.get(url)
        force_authenticate(request, user=user)
        response = self.get_response_as_view(request, actions={'get': 'list'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['url'] == client_url

        company_contact.delete()
        CandidateContact.objects.create(contact=user.contact)
        request = rf.get(url)
        force_authenticate(request, user=user)
        response = self.get_response_as_view(request, actions={'get': 'list'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['url'] == candidate_url

    def test_navigation_retrieve_with_role_parameter(self, user, roles, rf):
        client_url = 'client_url'
        manager_url = 'manager_url'
        candidate_url = 'candidate_url'
        url = '/core/extranetnavigations/?role=%s'

        ExtranetNavigation.objects.create(url=client_url, access_level=ExtranetNavigation.CLIENT)
        ExtranetNavigation.objects.create(url=manager_url, access_level=ExtranetNavigation.MANAGER)
        ExtranetNavigation.objects.create(url=candidate_url, access_level=ExtranetNavigation.CANDIDATE)

        CompanyContact.objects.create(contact=user.contact, role=CompanyContact.MANAGER)

        request = rf.get(url % roles[1].id)
        force_authenticate(request, user=user)
        response = self.get_response_as_view(request, actions={'get': 'list'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['url'] == manager_url

        request = rf.get(url % roles[2].id)
        force_authenticate(request, user=user)
        response = self.get_response_as_view(request, actions={'get': 'list'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['url'] == client_url

        request = rf.get(url % roles[0].id)
        force_authenticate(request, user=user)
        response = self.get_response_as_view(request, actions={'get': 'list'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['url'] == candidate_url

    def test_navigation_retrieve_unknown_role(self, rf, another_user):
        url = '/core/extranetnavigations/'
        request = rf.get(url)
        force_authenticate(request, user=another_user)
        response = self.get_response_as_view(request, actions={'get': 'list'})

        assert response.data['errors']['non_field_errors'] == ['Unknown user role']

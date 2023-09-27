import pytest
import mock
from django.contrib.sites.models import Site

from django.test.client import RequestFactory
from r3sourcer.apps.core.api.permissions import (
    SitePermissions, SiteContactPermissions, SiteMasterCompanyFilterBackend,
    SiteClosestCompanyFilterBackend, SiteRelatedClosestCompanyFilterBackend
)
from r3sourcer.apps.core.models import SiteCompany, CompanyContactRelationship
from rest_framework.request import Request


@pytest.fixture
def get_request():
    factory = RequestFactory()
    return Request(factory.get('sites/'))


@pytest.fixture
def post_request():
    factory = RequestFactory()
    return Request(factory.post('sites/'))


class TestSitePermissions:
    sp = SitePermissions()

    def test_has_permission_not_authenticate_user(self, get_request):
        assert not self.sp.has_permission(get_request, None)

    def test_has_permission_authenticate_user_get(self, user, get_request):
        get_request.user = user
        assert self.sp.has_permission(get_request, None)

    def test_has_permission_authenticate_user_post(self, user, post_request):
        post_request.user = user
        assert not self.sp.has_permission(post_request, None)

    def test_has_permission_superuser_get(self, superuser, get_request):
        get_request.user = superuser
        assert self.sp.has_permission(get_request, None)

    def test_has_permission_superuser_post(self, superuser, post_request):
        post_request.user = superuser
        assert self.sp.has_permission(post_request, None)

    def test_has_object_permission(self, site, user, get_request):
        get_request.user = user
        assert self.sp.has_object_permission(get_request, None, site)

    def test_has_object_permission_authenticate_user_post(self, site, user, post_request):
        post_request.user = user
        assert not self.sp.has_object_permission(post_request, None, site)

    def test_is_master_related(self, user, site):
        assert not self.sp.is_master_related(user, site)

    def test_not_global_permissions(self, user, site):
        sp = SitePermissions()
        sp.global_permissions = False
        assert sp.has_permission(get_request, None)

    def test_not_object_permissions(self, get_request, user, site):
        sp = SitePermissions()
        sp.object_permissions = False
        assert sp.has_object_permission(post_request, None, site)


@pytest.fixture
def site_company(company, site):
    site_company = SiteCompany(company=company, site=site)
    site_company.save()
    return site_company


@pytest.mark.django_db
class TestSiteContactPermissions:

    scp = SiteContactPermissions()

    def test_has_permission_not_authenticate_user(self, get_request):
        assert not self.scp.has_permission(get_request, None)

    def test_has_permission_authenticate_user_get(self, staff_user, get_request, staff_relationship, site_company):
        with mock.patch.object(get_request, 'get_host', return_value='test.tt'):
            get_request.user = staff_user
            assert self.scp.has_permission(get_request, None)

    def test_has_permission_authenticate_user_post(self, user, post_request):
        post_request.user = user
        assert not self.scp.has_permission(post_request, None)

    def test_is_master_related_successfully(self, staff_user, staff_relationship, site_company, get_request):
        with mock.patch.object(get_request, 'get_host', return_value='test.tt'):
            assert self.scp.is_master_related(staff_user, get_request)

    def test_is_master_related_unsuccessfully(self, staff_user, site_company, get_request):
        with mock.patch.object(get_request, 'get_host', return_value='test.tt'):
            assert not self.scp.is_master_related(staff_user, get_request)

    def test_has_object_permission(self, staff_user, staff_relationship, get_request, site_company):
        with mock.patch.object(get_request, 'get_host', return_value='test.tt'):
            get_request.user = staff_user
            assert self.scp.has_object_permission(get_request, None, site_company)

    def test_has_object_permission_unsuccessfully(self, user, post_request, site_company):
        post_request.user = user
        assert not self.scp.has_object_permission(post_request, None, site_company)

    def test_has_object_permission_successfully(self, staff_user, staff_relationship, post_request, site_company):
        staff_user.is_superuser = True
        staff_user.save()
        post_request.user = staff_user
        assert self.scp.has_object_permission(post_request, None, site_company)

    def test_has_permission_with_not_object_permission(self, get_request):
        self.scp.global_permissions = False
        assert self.scp.has_permission(get_request, None)

    def test_object_permissions_with_not_object_permission(self, get_request, site_company):
        self.scp.object_permissions = False
        assert self.scp.has_object_permission(get_request, None, site_company)


@pytest.mark.django_db
class TestSiteMasterCompanyFilterBackend:
    backend_filter = SiteMasterCompanyFilterBackend()

    def test_filter_list_queryset_superuser(self, superuser, get_request):
        get_request.user = superuser
        queryset = Site.objects.all()
        assert queryset == self.backend_filter.filter_list_queryset(get_request, queryset, None)

    @mock.patch('r3sourcer.apps.core.api.permissions.get_site_master_company')
    def test_filter_list_queryset_empty(self, mock_site_company, user, get_request, staff_relationship, company_other):
        mock_site_company.return_value = company_other
        get_request.user = user
        queryset = CompanyContactRelationship.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(queryset) != len(filtered)
        assert len(filtered) == 0

    def test_filter_list_queryset_successfully(self, staff_company_contact, company_rel, get_request, site_company):
        CompanyContactRelationship.objects.create(
            company_contact=staff_company_contact,
            company=company_rel.regular_company,
        )

        get_request.user = staff_company_contact.contact.user
        queryset = Site.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(filtered) == 2
        assert site_company.site in filtered


@pytest.mark.django_db
class TestSiteClosestCompanyFilterBackend:
    backend_filter = SiteClosestCompanyFilterBackend()

    def test_filter_list_queryset_superuser(self, superuser, get_request):
        get_request.user = superuser
        queryset = Site.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(queryset) == len(filtered)

    def test_filter_list_queryset_empty(self, user, get_request):
        get_request.user = user
        queryset = Site.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(queryset) != len(filtered)
        assert len(filtered) == 0

    def test_filter_list_queryset_successfully(self, staff_user, staff_relationship, get_request, site_company):
        get_request.user = staff_user
        queryset = Site.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(filtered) == 1
        assert site_company.site in filtered


class TestSiteRelatedClosestCompanyFilterBackend:
    backend_filter = SiteRelatedClosestCompanyFilterBackend()

    def test_filter_list_queryset_superuser(self, superuser, get_request):
        get_request.user = superuser
        queryset = SiteCompany.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(queryset) == len(filtered)

    def test_filter_list_queryset_is_staff(self, staff_user, staff_relationship, get_request, site_company):
        staff_user.is_staff = True
        staff_user.save()
        get_request.user = staff_user

        queryset = SiteCompany.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(queryset) == len(filtered)

    def test_filter_list_queryset_not_staff(self, staff_user, staff_relationship, get_request, site_company):
        get_request.user = staff_user

        queryset = SiteCompany.objects.all()
        filtered = self.backend_filter.filter_list_queryset(get_request, queryset, None)
        assert len(queryset) == len(filtered)

from urllib.parse import urlparse

from django.db.models import Q

from dry_rest_permissions.generics import DRYPermissions, DRYPermissionFiltersBase
from rest_framework import permissions

from r3sourcer.apps.core.models import SiteCompany

from ..utils.companies import get_master_companies, get_closest_companies, get_site_master_company
from ..utils.utils import get_host


class SitePermissions(DRYPermissions):
    def has_permission(self, request, view):
        if not self.global_permissions:
            return True

        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        else:
            return request.user and request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        if not self.object_permissions:
            return True

        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        is_superuser = request.user and request.user.is_superuser
        return is_superuser or self.is_master_related(request.user, obj)

    def is_master_related(self, user, obj):
        return False


class SiteContactPermissions(SitePermissions):
    def has_permission(self, request, view):
        if not self.global_permissions:
            return True

        return request.user and request.user.is_authenticated and self.is_master_related(request.user, request)

    def has_object_permission(self, request, view, obj):
        if not self.object_permissions:
            return True

        return request.user and request.user.is_authenticated and self.is_master_related(request.user, request)

    def is_master_related(self, user, request):
        contact = user.contact
        closest_company = None

        if contact.is_company_contact():
            site_master_company = get_site_master_company(request=request)
            company_contacts = contact.company_contact.filter(
                Q(relationships__company=site_master_company) |
                Q(relationships__company__regular_companies__master_company=site_master_company),
                relationships__active=True
            )

            if company_contacts.exists():
                closest_company = site_master_company

        if not closest_company:
            closest_company = user.contact.get_closest_company()

        return user.is_superuser or SiteCompany.objects.filter(
            company=closest_company, site__domain__iexact=get_host(request)
        ).exists()


class SiteMasterCompanyFilterBackend(DRYPermissionFiltersBase):
    action_routing = False

    def filter_list_queryset(self, request, queryset, view):
        # if request.user.is_superuser:
        #     return queryset

        if not hasattr(queryset, 'owned_by'):
            return queryset

        # NOTE: filter by current sub-domain
        site_master_company = get_site_master_company(request=request)

        return queryset.owned_by(site_master_company)

    def filter_candidate_queryset(self, request, queryset, view):
        return self.filter_list_queryset(request, queryset, view)


class SiteClosestCompanyFilterBackend(DRYPermissionFiltersBase):
    action_routing = True

    def filter_list_queryset(self, request, queryset, view):
        # if request.user.is_superuser:
        #     return queryset

        closest_companies = get_closest_companies(request)
        return queryset.filter(site_companies__company__in=closest_companies)


class SiteRelatedClosestCompanyFilterBackend(DRYPermissionFiltersBase):
    action_routing = True
    queryset_filter = 'site__site_companies__company__in'

    def filter_list_queryset(self, request, queryset, view):
        # if request.user.is_superuser:
        #     return queryset

        if request.user.is_staff and request.user.contact.is_master_related():
            related_companies = get_closest_companies(request)
        else:
            related_companies = get_master_companies(request)
        return queryset.filter(**{self.queryset_filter: related_companies})


class SiteRelatedViaPageCompanyFilterBackend(SiteRelatedClosestCompanyFilterBackend):
    queryset_filter = 'page__site__site_companies__company__in'


class ReadonlyOrIsSuperUser(DRYPermissions):
    """
    Would be used only for superusers.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class ReadOnly(DRYPermissions):
    """
    Readonly permissions.
    Would be used for permissions.SAFE_METHODS.
    """

    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)

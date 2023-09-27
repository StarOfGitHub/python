from rest_framework import permissions


class BaseEndpointPermission(permissions.BasePermission):
    """
    Base class for custom permissions using GlobalPermissions
    permission_name + http method name is codename of required GlobalPermission for a given view
    """
    permission_name = ''

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            method = request.method.lower()
            codename = self.permission_name + '_' + method

            if method == 'options':
                return True
            if request.user.has_permission(codename):
                return True
            if request.user.has_group_permission(codename):
                return True

        return False


class CompanyEndpointPermission(BaseEndpointPermission):
    permission_name = 'company_endpoint'


class ContactEndpointPermission(BaseEndpointPermission):
    permission_name = 'contact_endpoint'


class CompanyContactEndpointPermission(BaseEndpointPermission):
    permission_name = 'company_contact_endpoint'


class CandidateContactEndpointPermission(BaseEndpointPermission):
    permission_name = 'candidate_contact_endpoint'


class TimesheetEndpointPermission(BaseEndpointPermission):
    permission_name = 'timesheet_endpoint'

from django.conf.urls import url, include

from r3sourcer.apps.company_settings import views


urlpatterns = [
    # Permissions
    url(r'^permissions/all/$', views.GlobalPermissionListView.as_view(), name='global_permission_list'),
    url(r'^permissions/user/(?P<id>[\w\-]+)/set/$', views.SetUserGlobalPermissionView.as_view(), name='set_user_global_permission'),
    url(r'^permissions/user/(?P<id>[\w\-]+)/revoke/$', views.RevokeUserGlobalPermissionView.as_view(), name='revoke_user_global_permission'),
    url(r'^permissions/user/(?P<id>[\w\-]+)/groups/$', views.UserGroupListView.as_view(), name='user_group_list'),
    url(r'^permissions/user/(?P<id>[\w\-]+)/available_groups/$', views.UserAvailableGroupListView.as_view(), name='user_available_group_list'),
    url(r'^permissions/user/(?P<id>[\w\-]+)/$', views.UserGlobalPermissionListView.as_view(), name='user_global_permission_list'),
    url(r'^permissions/group/(?P<id>[\w\-]+)/add_user/$', views.AddUserToGroupView.as_view(), name='add_user_to_group'),
    url(r'^permissions/group/(?P<id>[\w\-]+)/remove_user/$', views.RemoveUserFromGroupView.as_view(), name='remove_user_from_group'),
    url(r'^permissions/group/(?P<id>[\w\-]+)/set/$', views.SetGroupGlobalPermissionView.as_view(), name='set_group_global_permission'),
    url(r'^permissions/group/(?P<id>[\w\-]+)/delete/$', views.CompanyGroupDeleteView.as_view(), name='company_group_delete'),
    url(r'^permissions/group/(?P<id>[\w\-]+)/revoke/$', views.RevokeGroupGlobalPermissionView.as_view(), name='revoke_group_global_permission'),
    url(r'^permissions/group/(?P<id>[\w\-]+)/$', views.GroupGlobalPermissionListView.as_view(), name='group_global_permission_list'),
    url(r'^permissions/groups/create/$', views.CompanyGroupCreateView.as_view(), name='company_group_create'),
    url(r'^permissions/groups/$', views.CompanyGroupListView.as_view(), name='company_group_list'),

    # Company settings
    url(r'^company_settings/users/$', views.CompanyUserListView.as_view(), name='company_users_list'),
    url(r'^company_settings/site/$', views.SiteCompanySettingsView.as_view(), name='site_company_settings'),
    url(r'^company_settings/$', views.CompanySettingsView.as_view(), name='company_settings'),

    # MYOB
    url(r'^company_settings/company_files/refresh/$', views.RefreshCompanyFilesView.as_view(), name='refresh_company_files'),
    url(r'^company_settings/company_files/check/$', views.CheckCompanyFilesView.as_view(), name='check_company_files'),
    url(r'^company_settings/company_files/(?P<id>[\w\-]+)/accounts/$', views.CompanyFileAccountsView.as_view(), name='company_file_accounts'),
    url(r'^company_settings/company_files/(?P<id>[\w\-]+)/accounts/refresh/$', views.RefreshMYOBAccountsView.as_view(), name='refresh_company_file_accounts'),
    url(r'^company_settings/company_files/$', views.UserCompanyFilesView.as_view(), name='user_company_files'),
    url(r'^company_settings/myob_accounts/refresh/$', views.RefreshMYOBAccountsView.as_view(), name='refresh_myob_accounts'),
    url(r'^company_settings/myob_accounts/$', views.CompanyFileAccountsView.as_view(), name='myob_accounts'),
    url(r'^company_settings/myob_authorization/$', views.MYOBAuthorizationView.as_view(), name='myob_authorization'),
    url(r'^company_settings/myob_settings/$', views.MYOBSettingsView.as_view(), name='myob_settings'),
    url(r'^company_settings/auth_data/$', views.MYOBAuthDataListView.as_view(), name='auth_data'),
    url(r'^company_settings/auth_data/(?P<id>[\w\-]+)/delete/$', views.MYOBAuthDataDeleteView.as_view(), name='auth_data_delete'),
    url(r'^company_settings/myob_api_key/$', views.MYOBAPIKeyView.as_view(), name='myob_api_key'),
]

from django.conf.urls import url

from r3sourcer.apps.core import views
from r3sourcer.apps.core.api import views as api_views
from r3sourcer.apps.core.api.languages import views as language_views


urlpatterns = [
    url(r'^core/invoices/(?P<id>[\w\-]+)/approve/$', views.ApproveInvoiceView.as_view(), name='approve_invoice'),
    url(r'^core/invoices/(?P<id>[\w\-]+)/sync/$', views.SyncInvoiceView.as_view(), name='sync_invoice'),
    url(r'^core/invoices/sync/$', views.SyncInvoicesView.as_view(), name='sync_invoices'),
    url(r'^core/users/trial/$', api_views.TrialUserView.as_view({'post': 'create'}), name='register_trial'),
    url(r'^core/users/roles/$', views.UserRolesView.as_view(), name='user_roles'),
    url(r'^core/users/(?P<id>[\w\-]+)/set_roles/$', views.SetRolesView.as_view(), name='set_roles'),
    url(r'^core/users/(?P<id>[\w\-]+)/revoke_roles/$', views.RevokeRolesView.as_view(), name='revoke_roles'),
    url(r'^core/users/timezone/$', views.UserTimezone.as_view(), name='user_timezone'),
    # new patterns
    url(r'^languages/', language_views.LanguageViewSet.as_view({'get': 'list'}), name='languages'),
]

from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^signin$', views.signin, name='signin'),
    url(r'^oauth2_redirect_uri$', views.authorized, name='authorized'),
    url(r'^cf_list$', views.cf_list, name='cf_list'),
    url(r'^cf_signin/(?P<cf_id>[0-9a-z-]{36})/$', views.cf_signin,
        name='cf_signin'),
    url(r'^cf_authorized/', views.cf_authorized, name='cf_authorized'),
]

app_name = 'myob'

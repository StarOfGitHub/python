from django.conf import settings
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.contrib import admin
from rest_framework_swagger.views import get_swagger_view

from r3sourcer.apps.core.api.contact_languages.urls import router as contact_language_router
from r3sourcer.apps.core.api.company_languages.urls import router as company_language_router
from r3sourcer.apps.core.api.bank_account_layouts.urls import router as bank_account_layout_router
from r3sourcer.apps.core.api.contact_bank_accounts.urls import router as contact_bank_account_router
from r3sourcer.apps.core.api.router import router
from r3sourcer.apps.core.api.viewsets import AppsList, ModelsList, FunctionsList
from r3sourcer.apps.core.views import FormView, RegisterFormView, OAuthJWTToken
from r3sourcer.apps.core.forms import CoreAdminAuthenticationForm
from r3sourcer.apps.logger.admin import admin_logger
from r3sourcer.apps.logger.api.viewsets import journal_list, journal_detail
from r3sourcer.apps.logger.main import autodiscover


autodiscover()

router.registry.append(('apps', AppsList, 'apps'))
router.registry.append(('models', ModelsList, 'models'))
router.registry.append(('functions', FunctionsList, 'functions'))

admin.site.login_form = CoreAdminAuthenticationForm
swagger_view = get_swagger_view(title='Endless API')

_urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^form-builds/(?P<company>.+)/(?P<pk>.+)/$', FormView.as_view(), name='form-builder-view'),
    url(r'^register/$', RegisterFormView.as_view(), name='form-builder-register'),
    url(r'^rosetta/', include('rosetta.urls')),
    url(r'^twilio/', include('r3sourcer.apps.twilio.urls', namespace='twilio')),
    url(r'^sms_interface/api/', include('r3sourcer.apps.sms_interface.urls', namespace='sms_interface')),
    url(r'^myob/', include('r3sourcer.apps.myob.urls', namespace='myob')),
    url(r'^admin/', admin_logger.urls),
    url(r'^_nested_admin/', include('nested_admin.urls')),
    url(r'^journal/(?P<app_path>.+)/(?P<model>.+)/(?P<pk>\d+?)/', journal_detail),
    url(r'^journal/(?P<app_path>.+)/(?P<model>.+)/', journal_list),
    url(r'^', include('r3sourcer.apps.billing.urls', namespace='billing')),
    url(r'^', include('r3sourcer.apps.company_settings.urls')),
    url(r'^', include('r3sourcer.apps.core.urls')),
    url(r'^', include('r3sourcer.apps.hr.urls')),
    url(r'^', include('r3sourcer.apps.skills.urls')),
    url(r'^', include('r3sourcer.apps.pricing.urls')),
    url(r'^', include((router.urls, 'api'), namespace='api')),
    url(r'^', include(('filer.urls', 'filer'), namespace='filer')),
    url(r'^admin/', include('loginas.urls')),
    url(r'^oauth2/token/$', OAuthJWTToken.as_view(), name='oauth2_token'),
    url(r'^oauth2/', include('oauth2_provider_jwt.urls', namespace='oauth2_provider')),
    url(r'^swagger/', swagger_view),
    # new api endpoints - refactor this in future
    url(r'^', include(contact_language_router.urls)),
    url(r'^', include(company_language_router.urls)),
    url(r'^', include(bank_account_layout_router.urls)),
    url(r'^', include(contact_bank_account_router.urls)),
]

urlpatterns = [
    url('^{}'.format(settings.DJANGO_STUFF_URL_PREFIX), include(_urlpatterns))
]

if settings.DEBUG and not settings.AWS_STORAGE_BUCKET_NAME:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

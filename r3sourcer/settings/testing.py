from .prod import *


TEST = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': env('POSTGRES_DB'),
        'USER': env('POSTGRES_USER'),
        'PASSWORD': env('POSTGRES_PASSWORD'),
        'HOST': env('POSTGRES_HOST'),
        'PORT': str(env('POSTGRES_PORT')),
    },
}

REST_FRAMEWORK = {
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.URLPathVersioning',
    'DEFAULT_FILTER_BACKENDS': (
        'r3sourcer.apps.core.api.permissions.SiteMasterCompanyFilterBackend',
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'r3sourcer.apps.core.api.filters.ApiOrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'r3sourcer.apps.core.api.pagination.ApiLimitOffsetPagination',
    'PAGE_SIZE': 10,
    'DATETIME_INPUT_FORMATS': ['iso-8601'],
    'EXCEPTION_HANDLER': 'r3sourcer.apps.core.api.views.core_exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'r3sourcer.apps.core.api.authentication.JWTAuthentication',
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
}

LOGGER_DB = 'testing'
LOGGER_ENABLED = False

REDIRECT_DOMAIN = 'r3sourcer.com'


def cities_light_uri(n): return 'file://%s' % os.path.join(
    BASE_DIR, 'r3sourcer/apps/core/tests/fixtures/django_cities', n
)

CITIES_LIGHT_COUNTRY_SOURCES = [
    cities_light_uri('country.txt')
]

CITIES_LIGHT_REGION_SOURCES = [
    cities_light_uri('regions.txt')
]

CITIES_LIGHT_CITY_SOURCES = [
    cities_light_uri('cities.txt')
]

CITIES_LIGHT_TRANSLATION_SOURCES = [
    cities_light_uri('translations.txt')
]

from rest_framework import routers
from .views import CompanyLanguageViewSet

router = routers.DefaultRouter()
router.register(r'companies/'
                r'(?P<company_id>[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})/'
                r'languages',
                CompanyLanguageViewSet)

from rest_framework import routers
from .views import ContactBankAccountViewSet

router = routers.DefaultRouter()
router.register(r'contacts/'
                r'(?P<contact_id>[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})/'
                r'bank_accounts',
                ContactBankAccountViewSet)

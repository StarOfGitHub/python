from rest_framework import routers
from .views import BankAccountLayoutViewSet

router = routers.DefaultRouter()
router.register(r'bank_account_layouts/'
                r'(?P<country_id>[a-zA-Z]{2})',
                BankAccountLayoutViewSet)

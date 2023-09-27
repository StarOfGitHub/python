from rest_framework import routers
from .views import LanguageViewSet

router = routers.DefaultRouter()
router.register(r'languages', LanguageViewSet)

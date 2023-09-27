from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.core.api.router import router

from .api import viewsets
from .models import TokenLogin


class LoginEndpoint(ApiEndpoint):

    model = TokenLogin
    viewset = viewsets.AuthViewSet
    fields = ('username', 'password')


router.register(endpoint=LoginEndpoint(), url='auth')
router.register(TokenLogin)

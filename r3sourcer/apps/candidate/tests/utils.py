from rest_framework.test import APITestCase, APIClient
from django.contrib.auth.models import AnonymousUser


class BaseTestCase(APITestCase):
    request_content_type = 'application/json'
    request_data_format = 'json'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.view_kwargs = {}

    def get_allowed_users(self):
        """
        Override this to lazily get allowed users
        :return: list of users to authorize in tests
        """
        return [AnonymousUser]

    def get_view_kwargs(self):
        """
        Override to lazily get reverse kwargs
        :return: dict with url kwargs
        """
        return self.view_kwargs

    def authorize_allowed_user(self):
        """
        Authorizes first allowed user to use in test requests
        :return: 
        """
        self.c.force_authenticate(user=self.get_allowed_users()[0])

    def get_url(self, view_name=None, args=None, kwargs=None):
        # return reverse(view_name or self.view_name,
        #                args=args or self.get_view_args(),
        #                kwargs=kwargs or self.get_view_kwargs())
        return ''

    def cancel_authorization(self):
        """
        removes authorization from self.c
        :return: 
        """
        self.c.force_authenticate()
        self.c.credentials()

    def make_request(self, method='GET', view_kwargs=None, data=None, **kwargs):
        prep_view_kwargs = self.get_view_kwargs() or {}
        prep_view_kwargs.update(view_kwargs or {})
        self.authorize_allowed_user()
        response = getattr(self.c, method.lower())(format=self.request_data_format,
                                                   path=self.get_url(kwargs=prep_view_kwargs),
                                                   data=data,
                                                   **kwargs)
        return response

    def setUp(self):
        """
        setups client class and it's methods properties with
        content_type(which is response format requested)
        format(which is encoding type of sent data)
        :return: 
        """
        self.c = APIClient()
        self.objects_cache = []

    def tearDown(self):
        self.cancel_authorization()
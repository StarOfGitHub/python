import mock
import pytest

from rest_framework import status
from rest_framework.test import force_authenticate

from r3sourcer.apps.activity.endpoints import ActivityEndpoint
from r3sourcer.apps.activity.models import Activity
from r3sourcer.apps.core.managers import AbstractObjectOwnerQuerySet


class ResourceMixin:
    endpoint_class = None
    actions = {
        'get': 'retrieve',
        'put': 'update',
        'post': 'create',
        'delete': 'destroy',
    }

    def get_response_as_view(self, request, pk=None, endpoint=None, actions=None):
        kwargs = {'request': request, 'partial': request.method.lower() == 'put'}
        if pk is not None:
            kwargs['pk'] = pk
        endpoint = endpoint or self.endpoint_class
        viewset = endpoint().get_viewset()
        view = viewset.as_view(actions or self.actions)
        response = view(**kwargs)
        response.render()
        return response


@pytest.mark.django_db
class TestDashboardModules(ResourceMixin):
    endpoint_class = ActivityEndpoint
    actions = {
        'get': 'list',
        'post': 'create'
    }

    @mock.patch.object(AbstractObjectOwnerQuerySet, 'owned_by')
    def test_get_activities(self, mock_owned, rf, primary_activity, secondary_activity):
        mock_owned.return_value = Activity.objects.filter(id=primary_activity.id)

        req = rf.get('/activity/activities/')
        force_authenticate(req, user=primary_activity.contact.user)

        resp_data = self.get_response_as_view(req)

        assert status.HTTP_200_OK == resp_data.status_code
        assert 'results' in resp_data.data
        assert len(resp_data.data['results']) == 1
        assert Activity.objects.all().count() == 2

    def test_get_activities_by_superuser(self, rf, primary_activity, secondary_activity):
        req = rf.get('/activity/activities/')

        primary_activity.contact.user.is_superuser = True

        force_authenticate(req, user=primary_activity.contact.user)

        resp_data = self.get_response_as_view(req)

        assert status.HTTP_200_OK == resp_data.status_code
        assert 'results' in resp_data.data
        assert len(resp_data.data['results']) == Activity.objects.all().count()

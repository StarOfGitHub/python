import pytest

from r3sourcer.apps.core.endpoints import CompanyAddressEndpoint


@pytest.mark.django_db
class TestCompanyAddressEndpoint:

    def get_response_as_view(self, actions, request):
        kwargs = {'request': request}
        viewset = CompanyAddressEndpoint().get_viewset()
        view = viewset.as_view(actions)
        response = view(**kwargs)
        response.render()
        return response

    def test_delete_action(self, rf):
        req = rf.post('/delete', data={'ids': [1]})

        response = self.get_response_as_view({'post': 'delete'}, req)

        assert response.data['status'] == 'success'

    def test_delete_action_without_ids(self, rf):
        req = rf.post('/delete')

        response = self.get_response_as_view({'post': 'delete'}, req)

        assert 'errors' in response.data
        assert response.status_code == 400

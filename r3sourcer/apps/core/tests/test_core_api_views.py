import mock
import pytest

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from r3sourcer.apps.core.models import SiteCompany, Contact, FormBuilder


@pytest.mark.django_db
class TestTrialUserView:

    def make_post_request(self, client, data=None):
        url = reverse('register_trial')
        return client.post(url, data=data)

    @mock.patch('r3sourcer.apps.core.api.views.send_trial_email.apply_async')
    def test_register_success(self, mock_trial, client, contact_phone):
        data = {
            'first_name': 'testuser42',
            'last_name': 'tester42',
            'email': 'test42@test.tt',
            'phone_mobile': contact_phone,
            'company_name': 'Test Company',
            'website': 'test',
            'country_code': 'et'
        }

        ct, _ = ContentType.objects.get_or_create(app_label='candidate', model='candidatecontact')
        FormBuilder.objects.get_or_create(content_type=ct)

        resp = self.make_post_request(client, data).json()

        assert resp['status'] == 'success'
        assert Contact.objects.filter(email='test42@test.tt', phone_mobile=contact_phone).exists()
        assert SiteCompany.objects.filter(
            site__domain='test',
            company__name='Test Company').exists()
        assert mock_trial.called

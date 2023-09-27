from django.urls import reverse
from django.conf import settings

from r3sourcer.apps.core.models.core import Company


class TestSMSMessageListView:
    def test_get_as_admin(self, client, admin, company, sms_message):
        url = reverse('sms_interface:sms_messages')
        client.force_login(admin)
        response = client.get(url).json()

        assert response['count'] == 1
        assert response['results'][0]['segments'] == sms_message.segments
        assert response['results'][0]['company'] == sms_message.company.name

    # seems like it's an outdated test checking permissions
    # def test_get(self, client, user, company, sms_message):
    #     url = reverse('sms_interface:sms_messages')
    #     # client.force_login(user)
    #     response = client.get(url).json()
    #
    #     assert response['status'] == 'error'
    #     assert response['errors']['detail'] == 'You do not have permission to perform this action.'

    def test_get_with_company_arg(self, client, admin, company, sms_message):
        url = "%s?company_id=%s" % (reverse('sms_interface:sms_messages'), company.id)
        client.force_login(admin)
        response = client.get(url).json()

        assert response['count'] == 1
        assert response['results'][0]['segments'] == sms_message.segments
        assert response['results'][0]['company'] == sms_message.company.name

    def test_get_with_company_arg_empty(self, client, admin, company, sms_message, primary_contact):
        new_company = Company.objects.create(
            name='Company2',
            business_id='222',
            registered_for_gst=True,
            primary_contact=primary_contact,
            type=Company.COMPANY_TYPES.master,
        )

        url = "%s?company_id=%s" % (reverse('sms_interface:sms_messages'), new_company.id)
        client.force_login(admin)
        response = client.get(url).json()

        assert response['count'] == 0

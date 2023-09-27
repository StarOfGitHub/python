import mock
import pytest

from r3sourcer.apps.email_interface import models


email_message = models.EmailMessage(message_id='msg_id', from_email='test@test.tt', to_addresses='test1@test.tt')

str_test_data = [
    (email_message, 'To test1@test.tt from test@test.tt'),
    (models.EmailBody(content='test', message=email_message), 'Message: msg_id'),
]


@pytest.mark.django_db
class TestStr:

    @pytest.mark.parametrize(['obj', 'str_result'], str_test_data)
    def test_str(self, obj, str_result):
        assert str(obj) == str_result


@pytest.mark.django_db
class TestEmailMessage:

    def test_has_text_message(self, fake_email, fake_email_text_body):
        assert fake_email.has_text_message()

    def test_has_text_message_none(self, fake_email):
        assert not fake_email.has_text_message()

    def test_has_html_message(self, fake_email, fake_email_html_body):
        assert fake_email.has_html_message()

    def test_has_html_message_none(self, fake_email):
        assert not fake_email.has_html_message()

    def test_get_text_body(self, fake_email, fake_email_text_body):
        res = fake_email.get_text_body()

        assert res == 'test'

    def test_get_text_body_none(self, fake_email):
        res = fake_email.get_text_body()

        assert res is None

    def test_get_html_body(self, fake_email, fake_email_html_body):
        res = fake_email.get_html_body()

        assert res == 'test'

    def test_get_html_body_none(self, fake_email):
        res = fake_email.get_html_body()

        assert res is None


@pytest.mark.django_db
class TestEmailTemplates:

    def test_default_email_templates_create(self, default_email_template):
        assert models.DefaultEmailTemplate.objects.filter(slug=default_email_template.slug).exists()

    def test_default_email_templates_update(self, default_email_template):
        template = default_email_template
        template.subject_template = "Test subject updated"
        template.save()
        assert models.DefaultEmailTemplate.objects.filter(subject_template="Test subject updated").exists()

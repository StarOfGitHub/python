import mock
import pytest

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.six import StringIO

from r3sourcer.apps.core.models import Country, Workflow, WorkflowNode


@pytest.mark.django_db
class TestCommands:

    @pytest.fixture
    def out(self):
        return StringIO()

    def test_createsuperuser_command(self, out):
        call_command('createsuper', '--noinput', email='test@test.tt',
                     phone_mobile='+12345678901', stdout=out)

        assert 'Superuser created successfully.' in out.getvalue()

    def test_createsuperuser_command_with_invalid_email(self, out):
        with pytest.raises(CommandError):
            call_command('createsuper', '--noinput', email='test',
                         phone_mobile='+12345678901', stdout=out)

    def test_createsuperuser_command_with_invalid_phone(self, out):
        with pytest.raises(CommandError):
            call_command('createsuper', '--noinput', email='test@test.tt',
                         phone_mobile='+12345', stdout=out)


@pytest.mark.django_db
class TestCitiesLightCurrencyCommands:

    @pytest.fixture
    def out(self):
        return StringIO()

    def test_cities_light_currency_on_existing_countries(self, out):
        call_command('cities_light_curr', '--force-import', 'country', stdout=out)
        country = Country.objects.get(code2='AU')

        assert country.currency == 'AUD'

    def test_cities_light_currency_no_countries(self, out):
        Country.objects.all().delete()
        call_command('cities_light_curr', '--force-import', 'country', stdout=out)
        country = Country.objects.get(code2='AU')

        assert country.currency == 'AUD'

    def test_cities_light_currency_no_countries_no_insert(self, out):
        Country.objects.all().delete()
        call_command('cities_light_curr', '--noinsert', '--force-import', 'country', stdout=out)

        assert Country.objects.all().count() == 0


@pytest.mark.django_db
class TestLoadWorkflowCommands:

    @pytest.fixture
    def out(self):
        return StringIO()

    def test_load_workflow(self, out):
        call_command('load_workflow', stdout=out)
        order_ct = ContentType.objects.get_by_natural_key(
            'core', 'order'
        )
        order_workflow = Workflow.objects.filter(model=order_ct)
        nodes = WorkflowNode.objects.filter(workflow=order_workflow)

        assert order_workflow.exists()
        assert nodes.count() == 5

    @mock.patch('builtins.open', side_effect=CommandError('test error'))
    def test_load_workflow_file_read_exception(self, mock_open, out):
        with pytest.raises(CommandError):
            call_command('load_workflow', stdout=out)

    def test_load_workflow_not_workflow_objects(self, out):
        mock_read = mock.mock_open(read_data='[{"model": "test"}]')

        with mock.patch('builtins.open', mock_read, create=True):
            with pytest.raises(CommandError):
                call_command('load_workflow', stdout=out)

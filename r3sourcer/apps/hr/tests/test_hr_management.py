import mock
import pytest

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.six import StringIO

from r3sourcer.apps.core.models import Workflow, WorkflowNode


@pytest.mark.django_db
class TestLoadWorkflowCommand:

    @pytest.fixture
    def out(self):
        return StringIO()

    def test_load_hr_workflow(self, out):
        call_command('load_hr_workflow', stdout=out)
        jobsite_ct = ContentType.objects.get_by_natural_key(
            'hr', 'jobsite'
        )
        jobsite_workflow = Workflow.objects.filter(model=jobsite_ct)
        nodes = WorkflowNode.objects.filter(workflow=jobsite_workflow)

        assert jobsite_workflow.exists()
        assert nodes.count() > 0

    @mock.patch('builtins.open', side_effect=Exception('test error'))
    def test_load_hr_workflow_file_read_exception(self, mock_open, out):
        with pytest.raises(CommandError):
            call_command('load_hr_workflow', stdout=out)

    def test_load_hr_workflow_not_workflow_objects(self, out):
        mock_read = mock.mock_open(read_data='[{"model": "test"}]')

        with mock.patch('builtins.open', mock_read, create=True):
            with pytest.raises(CommandError):
                call_command('load_hr_workflow', stdout=out)

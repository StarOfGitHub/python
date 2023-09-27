import mock
import pytest
import uuid

from r3sourcer.apps.core.models import WorkflowNode, WorkflowObject, Company
from r3sourcer.apps.core.workflow import (
    WorkflowProcess, CompanyRelState60, OrderState50, OrderState90
)
from django_mock_queries.query import MockSet, MockModel
from django.utils.translation import ugettext_lazy as _


states = MockSet(
    MockModel(object_id=1, state=MockModel(
        number=10, workflow=MockModel(model=1), company_workflow_nodes=MockModel(company=1)
    ), active=True, created_at=1),
    MockModel(object_id=1, state=MockModel(
        number=20, workflow=MockModel(model=1), company_workflow_nodes=MockModel(company=1)
    ), active=True, created_at=2)
)


@pytest.mark.django_db
class TestWorkflowProcess:
    @pytest.fixture
    def workflow_process(self, active_states):
        with mock.patch.object(WorkflowProcess, 'get_active_states', return_value=active_states):
            yield WorkflowProcess()

    @pytest.fixture
    def workflow_proc(self):
        with mock.patch.object(WorkflowProcess, 'content_type', new_callable=mock.PropertyMock) as mock_content:
            mock_content.return_value = 1
            process = WorkflowProcess()
            process.id = 1
            yield process

    @pytest.fixture
    def active_states(self):
        qs = MockSet(
            MockModel(state=self.get_node(10), active=True, created_at=1),
            MockModel(state=self.get_node(20), active=True, created_at=2)
        )
        return qs

    def _get_company(self):
        return Company.objects.get(name='New C')

    def is_test_function_positive(self):
        return True

    def is_test_function_negative(self):
        return False

    def get_node(self, number):
        return WorkflowNode.objects.get(number=number)

    def test_is_allowed_state_successfully(self, workflow_process):
        assert workflow_process.is_allowed(self.get_node(40))

    def test_is_allowed_state_unsuccessfully(self, workflow_process):
        assert not workflow_process.is_allowed(self.get_node(0))

    def test_is_allowed_state_with_func_requirement_successfully(self, workflow_process):
        setattr(workflow_process, "is_test_function", self.is_test_function_positive)
        assert workflow_process.is_allowed(self.get_node(30))

    def test_is_allowed_state_with_requirement_unsuccessfully(self, workflow_process):
        setattr(workflow_process, "is_test_function", self.is_test_function_negative)
        assert not workflow_process.is_allowed(self.get_node(30))

    def test_is_allowed_state_exists(self, workflow_process):
        assert not workflow_process.is_allowed(self.get_node(10))

    def test_is_allowed_state_none(self, workflow_process):
        assert not workflow_process.is_allowed(None)

    def test_is_allowed_withour_required_states(self, workflow_process):
        assert workflow_process.is_allowed(self.get_node(70))

    def test_available_states_for_creation_one_result(self, workflow_process):
        setattr(workflow_process, "get_closest_company", self._get_company)
        available_states = workflow_process.get_available_states_for_creation()
        assert len(available_states) == 4
        assert available_states[0] == self.get_node(40)

    def test_available_states_for_creation_multiple_result(self, workflow_process):
        setattr(workflow_process, "is_test_function", self.is_test_function_positive)
        setattr(workflow_process, "get_closest_company", self._get_company)
        available_states = workflow_process.get_available_states_for_creation()
        assert len(available_states) == 5
        for available in available_states:
            assert available.number in [
                30, 40, 70, 100, 120,
            ]

    def test_required_message_state_is_already_active(self, workflow_process):
        message = workflow_process.get_required_message(self.get_node(20))
        assert message == _('State is already active')

    def test_required_message_state_is_required(self, workflow_process):
        message = workflow_process.get_required_message(self.get_node(0))
        assert message == _("State 40 is required.")

    def test_required_message_states_are_required(self, workflow_process):
        message = workflow_process.get_required_message(self.get_node(50))
        assert message == _("State 30 and State 40 are required.")

    def test_required_message_alternative_states_are_required(self, workflow_process):
        message = workflow_process.get_required_message(self.get_node(60))
        assert message == _("State 40 or State 50 are required.")  # is required

    def test_required_message_function_is_required(self, workflow_process):
        setattr(workflow_process, "is_test_function", self.is_test_function_negative)
        message = workflow_process.get_required_message(self.get_node(30))
        assert message == _("is_test_function is required.")

    def test_get_required_messages_no_states(self, workflow_process):
        setattr(workflow_process, "is_test_function", self.is_test_function_negative)
        messages = workflow_process.get_required_messages(self.get_node(30), False)
        assert messages == [_("is_test_function is required.")]

    def test_required_message_default_message(self, workflow_process):
        node = self.get_node(30)
        node.rules = None
        message = workflow_process.get_required_message(node)
        assert message == ''

    @mock.patch.object(WorkflowObject, 'objects', new_callable=mock.PropertyMock)
    def test_get_active_states(self, mock_objects, workflow_proc):
        mock_objects.return_value = states

        with mock.patch.object(WorkflowProcess, 'get_closest_company', return_value=1):
            wp_active_states = workflow_proc.get_active_states()

        assert wp_active_states.count() == 2
        assert wp_active_states.first().state.number == 20
        assert wp_active_states.last().state.number == 10

    @mock.patch.object(WorkflowProcess, 'content_type',
                       new_callable=mock.PropertyMock)
    @mock.patch.object(WorkflowObject, 'objects',
                       new_callable=mock.PropertyMock)
    def test_get_active_states_without_id(self, mock_objects, mock_content):
        mock_content.return_value = 1
        mock_objects.return_value.none.return_value = MockSet()
        process = WorkflowProcess()

        wp_active_states = process.get_active_states()

        assert wp_active_states.count() == 0

    @mock.patch.object(WorkflowObject, 'objects',
                       new_callable=mock.PropertyMock)
    def test_get_current_state(self, mock_objects, workflow_proc):
        mock_objects.return_value = states

        with mock.patch.object(WorkflowProcess, 'get_closest_company', return_value=1):
            current_state = workflow_proc.get_current_state()

        assert current_state.number == 20

    @mock.patch.object(WorkflowObject, 'objects',
                       new_callable=mock.PropertyMock)
    def test_get_current_state_exception(self, mock_objects, workflow_proc):
        mock_objects.side_effect = WorkflowObject.DoesNotExist

        current_state = workflow_proc.get_current_state()

        assert current_state is None

    def test_get_rule_sign(self):
        process = WorkflowProcess()

        sign = process._get_rule_sign(['or', 10])

        assert sign == 'or'

    def test_get_rule_sign_default(self):
        process = WorkflowProcess()

        sign = process._get_rule_sign([])

        assert sign == 'and'

    @mock.patch.object(WorkflowProcess, '_or_check', return_value=True)
    @mock.patch.object(WorkflowProcess, '_get_rule_sign', return_value='or')
    def test_check_condition_list(self, mock_sign, mock_or_check):
        process = WorkflowProcess()

        cond = process._check_condition([])

        assert cond
        assert mock_or_check.called

    @mock.patch.object(WorkflowProcess, '_and_check', return_value=True)
    @mock.patch.object(WorkflowProcess, '_get_rule_sign', return_value='and')
    def test_check_condition_list_and(self, mock_sign, mock_and_check):
        process = WorkflowProcess()

        cond = process._check_condition([])

        assert cond
        assert mock_and_check.called

    @mock.patch.object(WorkflowProcess, '_check_state', return_value=True)
    def test_check_condition_int(self, mock_check):
        process = WorkflowProcess()

        cond = process._check_condition(10)

        assert cond
        assert mock_check.called

    @mock.patch.object(WorkflowProcess, '_check_function', return_value=True)
    def test_check_condition_str(self, mock_check):
        process = WorkflowProcess()

        cond = process._check_condition('test_func')

        assert cond
        assert mock_check.called

    def test_check_condition_none(self):
        process = WorkflowProcess()

        cond = process._check_condition(None)

        assert cond

    def test_get_state_name(self):
        process = WorkflowProcess()

        cond = process._get_state_name(10)

        assert cond == 'State 10'

    def test_get_state_name_state_not_exists(self):
        process = WorkflowProcess()

        cond = process._get_state_name(77)

        assert cond == '77'

    @mock.patch.object(WorkflowProcess, '_get_or_message', return_value='or message')
    @mock.patch.object(WorkflowProcess, '_get_rule_sign', return_value='or')
    def test_get_message_for_condition_list_or(self, mock_sign, mock_or_mes):
        mock_sign.return_value = 'or'
        mock_or_mes.return_value = 'or message'

        process = WorkflowProcess()

        cond = process._get_message_for_condition([], None)

        assert cond == 'or message'

    @mock.patch.object(WorkflowProcess, '_get_and_message', return_value='and message')
    @mock.patch.object(WorkflowProcess, '_get_rule_sign', return_value='and')
    def test_get_message_for_condition_list_and(self, mock_sign, mock_and_mes):
        process = WorkflowProcess()

        cond = process._get_message_for_condition([], None)

        assert cond == 'and message'

    @mock.patch.object(WorkflowProcess, '_get_state_name', return_value='message')
    @mock.patch.object(WorkflowProcess, '_check_state', return_value=False)
    def test_get_message_for_condition_int(self, mock_state, mock_message):
        process = WorkflowProcess()

        cond = process._get_message_for_condition(1, None)

        assert cond == 'message'

    @mock.patch.object(WorkflowProcess, '_get_function_name', return_value='message')
    @mock.patch.object(WorkflowProcess, '_check_function', return_value=False)
    def test_get_message_for_condition_func(self, mock_check, mock_message):
        process = WorkflowProcess()

        cond = process._get_message_for_condition('test', None)

        assert cond == 'message'

    @mock.patch.object(WorkflowProcess, '_check_function', return_value=True)
    def test_get_message_for_condition_default(self, mock_check):
        process = WorkflowProcess()

        cond = process._get_message_for_condition('test', None)

        assert cond == ''

    def test_workflow(self, workflow_process):
        workflow_process.workflow(self.get_node(30))

        not_active_states = workflow_process.active_states.filter(
            active=False
        ).values_list('state__number', flat=True)

        assert set(not_active_states) == {10, 20}

    def test_workflow_without_rules(self, workflow_process):
        workflow_process.workflow(self.get_node(120))

        active_states = workflow_process.active_states.filter(
            active=True
        ).values_list('state__number', flat=True)

        assert set(active_states) == {10, 20}

    def test_workflow_all_active(self, workflow_process):
        workflow_process.workflow(self.get_node(100))

        not_active_states = workflow_process.active_states.filter(
            active=True
        ).values_list('state__number', flat=True)

        assert set(not_active_states) == {10, 20}

    def test_workflow_no_active_rule(self, workflow_process):
        workflow_process.workflow(self.get_node(110))

        not_active_states = workflow_process.active_states.filter(
            active=True
        ).values_list('state__number', flat=True)

        assert set(not_active_states) == {10, 20}

    @mock.patch.object(WorkflowProcess, 'content_type', return_value=None)
    def test_workflow_actions(self, mock_content_type, workflow_process):
        workflow_process.workflow(self.get_node(80))

        not_active_states = workflow_process.active_states.filter(
            active=False
        ).values_list('state__number', flat=True)

        assert set(not_active_states) == {10, 20}
        assert mock_content_type.called

    def test_workflow_action_not_exists(self, workflow_process):
        workflow_process.workflow(self.get_node(90))

        not_active_states = workflow_process.active_states.filter(
            active=False
        ).values_list('state__number', flat=True)

        assert set(not_active_states) == {10, 20}

    @mock.patch.object(WorkflowObject, 'model_object', new_callable=mock.PropertyMock)
    @mock.patch.object(WorkflowObject, 'validate_object', return_value=None)
    @mock.patch.object(WorkflowProcess, 'content_type', new_callable=mock.PropertyMock)
    def test_create_state(self, mock_content_type, mock_validate,
                          mock_model_obj, workflow_ct, workflow_process):
        mock_content_type.return_value = workflow_ct

        uid = uuid.uuid4()
        workflow_process.id = uid

        mock_company = mock.MagicMock()
        mock_company.return_value = self._get_company()

        workflow_process.get_closest_company = mock_company
        workflow_process.create_state(10)

        assert WorkflowObject.objects.get(
            object_id=uid, state__number=10, active=True
        )

    @mock.patch.object(WorkflowObject, 'model_object', new_callable=mock.PropertyMock)
    @mock.patch.object(WorkflowObject, 'validate_object', return_value=None)
    @mock.patch.object(WorkflowProcess, 'content_type', new_callable=mock.PropertyMock)
    @mock.patch('r3sourcer.apps.core.workflow.get_site_master_company')
    def test_create_state_no_closest_company(self, mock_default_company,
                                             mock_content_type, mock_validate,
                                             mock_model_obj, workflow_ct,
                                             workflow_process):
        mock_content_type.return_value = workflow_ct
        mock_default_company.return_value = self._get_company()

        uid = uuid.uuid4()
        workflow_process.id = uid

        mock_company = mock.MagicMock()
        mock_company.return_value = None

        workflow_process.get_closest_company = mock_company
        workflow_process.create_state(10)

        assert WorkflowObject.objects.get(
            object_id=uid, state__number=10, active=True
        )

    @mock.patch.object(WorkflowObject, 'model_object', new_callable=mock.PropertyMock)
    @mock.patch.object(WorkflowObject, 'validate_object', return_value=None)
    @mock.patch.object(WorkflowProcess, 'content_type', new_callable=mock.PropertyMock)
    @mock.patch('r3sourcer.apps.core.workflow.get_site_master_company')
    def test_create_state_no_state(self, mock_default_company,
                                   mock_content_type, mock_validate,
                                   mock_model_obj, workflow_ct,
                                   workflow_process):
        mock_content_type.return_value = workflow_ct
        mock_default_company.return_value = self._get_company()

        uid = uuid.uuid4()
        workflow_process.id = uid

        mock_company = mock.MagicMock()
        mock_company.return_value = None

        workflow_process.get_closest_company = mock_company
        workflow_process.create_state(200)

        assert not WorkflowObject.objects.filter(
            object_id=uid, state__number=200, active=True
        ).exists()


class TestCompanyRelState60:

    def test_check(self):
        mock_obj = mock.MagicMock()
        mock_obj.is_business_id_set.return_value = True

        state = CompanyRelState60()

        assert state.check(mock_obj)

    def test_check_false(self):
        mock_obj = mock.MagicMock()
        mock_obj.is_business_id_set.return_value = False

        state = CompanyRelState60()

        assert not state.check(mock_obj)


class TestOrderState50:

    def test_check(self):
        state = OrderState50()

        assert state.check(None)


class TestOrderState90:

    def test_check(self):
        state = OrderState90()

        assert state.check(None)

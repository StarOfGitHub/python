import mock
import pytest

from django_mock_queries.query import MockSet, MockModel

from r3sourcer.apps.acceptance_tests import models


questions = MockSet(
    MockModel(id=1, workflow_object_answers=MockModel(workflow_object_id=1, score=3)),
    MockModel(id=2, workflow_object_answers=MockModel(workflow_object_id=1, score=5)),
)
questions_with_excluded = MockSet(
    MockModel(id=1, workflow_object_answers=MockModel(workflow_object_id=1, score=3)),
)

@pytest.mark.django_db
class TestAcceptanceTest:
    def test_str(self, acceptance_test):
        assert str(acceptance_test) == acceptance_test.test_name

    def test_get_filtered_questions(self, acceptance_test, answer, excluded_question_answer, answer_wrong):
        assert acceptance_test.acceptance_test_questions.filter(exclude_from_score=False).count() == 1


@pytest.mark.django_db
class TestAcceptanceTestSkill:
    def test_str(self, acceptance_test_skill):
        assert str(acceptance_test_skill) == "{}, {}".\
            format(str(acceptance_test_skill.acceptance_test),
                   str(acceptance_test_skill.skill))

    def test_get_all_questions_with_result(self, acceptance_test_skill,
                                           answer):
        assert acceptance_test_skill.get_all_questions().count() == 1


@pytest.mark.django_db
class TestAcceptanceTestQuestion:
    def test_str(self, question):
        assert str(question) == question.question

    def test_get_correct_answers(self, question, answer):
        assert question.get_correct_answers().count() == 1

    def test_get_all_answers(self, question, answer, answer_wrong):
        assert question.get_all_answers().count() == 2


@pytest.mark.django_db
class TestAcceptanceTestAnswer:
    def test_str(self, answer):
        assert str(answer) == 'question: answer'


@pytest.mark.django_db
class TestAcceptanceTestWorkflowNode:
    @pytest.fixture
    def at_wf_obj(self):
        return models.AcceptanceTestWorkflowNode()

    def test_str(self, at_wf_obj):
        type(at_wf_obj).acceptance_test = mock.PropertyMock(return_value='test')
        type(at_wf_obj).company_workflow_node = mock.PropertyMock(return_value='test')

        assert str(at_wf_obj) == 'test, test'

    def test_get_all_questions(self, at_wf_obj):
        a_test = mock.PropertyMock()
        type(at_wf_obj).acceptance_test = a_test
        type(a_test.return_value).acceptance_test_questions = mock.PropertyMock(
            return_value=MockSet(MockModel(id=1), MockModel(id=2))
        )

        assert at_wf_obj.get_all_questions().count() == 2

    def test_get_score_none(self, at_wf_obj):
        assert at_wf_obj.get_score(None) == 0

    def test_get_score(self, at_wf_obj):
        with mock.patch.object(at_wf_obj, 'get_scored_questions', return_value=questions):
            assert at_wf_obj.get_score(1) == 4

    def test_get_score_with_excluded(self, at_wf_obj):
        with mock.patch.object(at_wf_obj, 'get_scored_questions', return_value=questions_with_excluded):
            assert at_wf_obj.get_score(1) == 3

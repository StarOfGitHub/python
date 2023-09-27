from django.db.models import Avg

from r3sourcer.apps.acceptance_tests import models
from r3sourcer.apps.core.api.serializers import ApiBaseModelSerializer


class AcceptanceTestSerializer(ApiBaseModelSerializer):

    class Meta:
        model = models.AcceptanceTest
        fields = (
            'test_name', 'description', 'valid_from', 'valid_until', 'is_active', 'id',
            {
                'acceptance_test_questions': (
                    'id', 'question', 'details', 'order', 'type', 'pictures', 'exclude_from_score',
                    {
                        'acceptance_test_answers': ('id',  'answer', 'order', 'score', ),
                    },
                ),
                'acceptance_tests_skills': ('id', 'skill'),
                'acceptance_tests_tags': ('id', 'tag'),
                'acceptance_tests_industries': ('id', 'industry'),
                'acceptance_tests_workflow_nodes': ('id', 'company_workflow_node'),
            }
        )


class AcceptanceTestSerializerAll(ApiBaseModelSerializer):

    class Meta:
        model = models.AcceptanceTest
        fields = (
            'test_name', 'description', 'id',
            {
                'acceptance_test_questions': (
                    'id', 'question', 'details', 'order', 'type', 'pictures', 'exclude_from_score',
                    {
                        'acceptance_test_answers': ('id',  'answer', 'order', 'score', ),
                    },
                ),
                'acceptance_tests_skills': ({'skill': ('id',)},),
                'acceptance_tests_tags': ({'tag': ('id',)},),
                'acceptance_tests_industries': ({'industry': ('id',)},),
            }
        )


class AcceptanceTestQuestionPictureSerializerAll(ApiBaseModelSerializer):

    class Meta:
        model = models.AcceptanceTestQuestionPicture
        fields = '__all__'


class AcceptanceTestWorkflowNodeSerializer(ApiBaseModelSerializer):

    method_fields = ('score', )

    class Meta:
        model = models.AcceptanceTestWorkflowNode
        fields = ('id', 'acceptance_test', 'company_workflow_node')

    def __init__(self, *args, **kwargs):
        self.workflow_object_id = kwargs.pop('workflow_object_id', None)

        super().__init__(*args, **kwargs)

    def get_score(self, obj):
        return obj.get_score(self.workflow_object_id)


class AcceptanceTestCandidateQuestionSerializer(ApiBaseModelSerializer):

    method_fields = ('answer', )

    class Meta:
        model = models.AcceptanceTestQuestion
        fields = ('question', 'details', 'exclude_from_score')

    def get_answer(self, obj):
        object_id = self.context['object_id']
        workflow_node = self.context['workflow_node']
        object_answer = obj.workflow_object_answers.filter(
            workflow_object__object_id=object_id,
            workflow_object__state=workflow_node
        ).first()

        return object_answer and {
            'answer': object_answer.answer_text or object_answer.answer.answer,
            'score': object_answer.score
        }


class AcceptanceTestCandidateWorkflowSerializer(ApiBaseModelSerializer):

    method_fields = ('score', 'questions')

    class Meta:
        model = models.AcceptanceTestWorkflowNode
        fields = ('id', 'acceptance_test', 'company_workflow_node')

    def __init__(self, *args, **kwargs):
        self.object_id = kwargs.pop('object_id', None)

        super().__init__(*args, **kwargs)

    def get_score(self, obj):
        return obj.get_scored_questions().filter(
            workflow_object_answers__workflow_object__object_id=self.object_id,
            workflow_object_answers__workflow_object__state=obj.company_workflow_node.workflow_node
        ).aggregate(score_avg=Avg('workflow_object_answers__score'))['score_avg'] or 0

    def get_questions(self, obj):
        all_questions = obj.get_all_questions().order_by('order')

        return AcceptanceTestCandidateQuestionSerializer(all_questions, many=True, context={
            'object_id': self.object_id,
            'workflow_node': obj.company_workflow_node.workflow_node
        }).data


class FormAcceptanceTestCandidateQuestionSerializer(ApiBaseModelSerializer):

    method_fields = ('answer', )

    class Meta:
        model = models.AcceptanceTestQuestion
        fields = ('id', 'question', 'details', 'exclude_from_score')

    def get_answer(self, obj):
        object_id = self.context['object_id']
        workflow_node = self.context['workflow_node']
        object_answer = obj.workflow_object_answers.filter(
            workflow_object__object_id=object_id,
            workflow_object__state=workflow_node
        ).first()

        return object_answer and {
            'answer': object_answer.answer_text or object_answer.answer.answer,
        }


class FormAcceptanceTestCandidateWorkflowSerializer(ApiBaseModelSerializer):

    method_fields = ('questions',)

    class Meta:
        model = models.AcceptanceTestWorkflowNode
        fields = ('id', 'company_workflow_node', {'acceptance_test': ('id', '__str__', 'test_name', {
            'acceptance_tests_skills': ({'skill': ('id',)},),
        },), }
                  )

    def __init__(self, *args, **kwargs):
        self.object_id = kwargs.pop('object_id', None)

        super().__init__(*args, **kwargs)


    def get_questions(self, obj):
        all_questions = obj.get_all_questions().order_by('order')

        return FormAcceptanceTestCandidateQuestionSerializer(all_questions, many=True, context={
            'object_id': self.object_id,
            'workflow_node': obj.company_workflow_node.workflow_node
        }).data


class WorkflowObjectAnswerSerializer(ApiBaseModelSerializer):

    class Meta:
        model = models.WorkflowObjectAnswer
        fields = ('id', 'acceptance_test_question', 'workflow_object', 'answer', 'answer_text', 'score', 'exclude')

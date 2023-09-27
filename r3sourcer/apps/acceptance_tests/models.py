from django.db import models
from django.utils.translation import ugettext_lazy as _
from easy_thumbnails.fields import ThumbnailerImageField

from model_utils import Choices

from r3sourcer.apps.core.models import Tag, CompanyWorkflowNode, WorkflowObject, Company
from r3sourcer.helpers.models.abs import UUIDModel
from r3sourcer.apps.skills.models import Skill
from r3sourcer.apps.pricing.models import Industry


class AcceptanceTest(UUIDModel):

    test_name = models.CharField(
        max_length=255,
        verbose_name=_("Test Name")
    )

    description = models.TextField(
        verbose_name=_("Description"),
        blank=True
    )

    valid_from = models.DateField(
        verbose_name=_("Valid From")
    )

    valid_until = models.DateField(
        verbose_name=_("Valid Until"),
        null=True,
        blank=True
    )

    is_active = models.BooleanField(
        verbose_name=_("Active"),
        default=False
    )

    skills = models.ManyToManyField(
        Skill,
        related_name='acceptance_tests',
        verbose_name=_("Related Skills"),
        through='AcceptanceTestSkill'
    )

    tags = models.ManyToManyField(
        Tag,
        related_name='acceptance_tests',
        verbose_name=_("Related Tags"),
        through='AcceptanceTestTag'
    )

    industries = models.ManyToManyField(
        Industry,
        related_name='acceptance_tests',
        verbose_name=_("Related Industries"),
        through='AcceptanceTestIndustry'
    )

    class Meta:
        verbose_name = _("Acceptance Test")
        verbose_name_plural = _("Acceptance Tests")

    def __str__(self):
        return self.test_name

    @property
    def score(self):
        return self.acceptance_test_questions.filter(exclude_from_score=False).aggregate(score=models.Avg('acceptance_test_answers__score'))['score']


class AcceptanceTestQuestionPicture(UUIDModel):
    acceptance_test_question = models.ForeignKey(
        'acceptance_tests.AcceptanceTestQuestion',
        on_delete=models.CASCADE,
        related_name='pictures',
        verbose_name=_("Acceptance Test Question Picture")
    )
    picture = ThumbnailerImageField(
        upload_to='acceptance_test_pictures',
        max_length=255,
    )

    class Meta:
        verbose_name = _("Acceptance Test Question Picture")
        verbose_name_plural = _("Acceptance Tests Question Pictures")


class AcceptanceTestSkill(UUIDModel):
    acceptance_test = models.ForeignKey(
        'acceptance_tests.AcceptanceTest',
        on_delete=models.CASCADE,
        related_name='acceptance_tests_skills',
        verbose_name=_("Acceptance Test")
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name='acceptance_tests_skills',
        verbose_name=_("Skill")
    )

    class Meta:
        verbose_name = _("Acceptance Test Skill")
        verbose_name_plural = _("Acceptance Tests and Skills")

    def __str__(self):
        return '{}, {}'.format(str(self.acceptance_test), str(self.skill))

    def get_all_questions(self):
        return self.acceptance_test.acceptance_test_questions.all()


class AcceptanceTestTag(UUIDModel):
    acceptance_test = models.ForeignKey(
        AcceptanceTest,
        on_delete=models.CASCADE,
        related_name='acceptance_tests_tags',
        verbose_name=_("Acceptance Test")
    )

    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name='acceptance_tests_tags',
        verbose_name=_("Tag")
    )

    class Meta:
        verbose_name = _("Acceptance Test Tag")
        verbose_name_plural = _("Acceptance Tests and Tags")

    def __str__(self):
        return '{}, {}'.format(str(self.acceptance_test), str(self.tag))

    def get_all_questions(self):
        return self.acceptance_test.acceptance_test_questions.all()


class AcceptanceTestIndustry(UUIDModel):
    acceptance_test = models.ForeignKey(
        AcceptanceTest,
        on_delete=models.CASCADE,
        related_name='acceptance_tests_industries',
        verbose_name=_("Acceptance Test")
    )

    industry = models.ForeignKey(
        Industry,
        on_delete=models.CASCADE,
        related_name='acceptance_tests_industries',
        verbose_name=_("Industry")
    )

    class Meta:
        verbose_name = _("Acceptance Test Industry")
        verbose_name_plural = _("Acceptance Tests and Industries")

    def __str__(self):
        return '{}, {}'.format(str(self.acceptance_test), str(self.industry))

    def get_all_questions(self):
        return self.acceptance_test.acceptance_test_questions.all()


class AcceptanceTestWorkflowNode(UUIDModel):
    acceptance_test = models.ForeignKey(
        AcceptanceTest,
        on_delete=models.CASCADE,
        related_name='acceptance_tests_workflow_nodes',
        verbose_name=_("Acceptance Test")
    )

    company_workflow_node = models.ForeignKey(
        CompanyWorkflowNode,
        on_delete=models.CASCADE,
        related_name='acceptance_tests_workflow_nodes',
        verbose_name=_("Workflow Node")
    )

    class Meta:
        verbose_name = _("Acceptance Test Workflow Node")
        verbose_name_plural = _("Acceptance Tests and Workflow Nodes")

    def __str__(self):
        return '{}, {}'.format(str(self.acceptance_test), str(self.company_workflow_node))

    def get_all_questions(self):
        return self.acceptance_test.acceptance_test_questions.all()

    def get_scored_questions(self):
        return self.acceptance_test.acceptance_test_questions.filter(exclude_from_score=False)

    def get_score(self, workflow_object_id):
        if workflow_object_id is None:
            return 0

        return self.get_scored_questions().filter(
            workflow_object_answers__workflow_object_id=workflow_object_id,
            workflow_object_answers__score__gt=0,
        ).aggregate(score_avg=models.Avg('workflow_object_answers__score'))['score_avg'] or 0


class AcceptanceTestQuestion(UUIDModel):
    acceptance_test = models.ForeignKey(
        AcceptanceTest,
        on_delete=models.CASCADE,
        related_name='acceptance_test_questions',
        verbose_name=_("Acceptance Test")
    )

    question = models.CharField(
        max_length=255,
        verbose_name=_("Question")
    )

    details = models.TextField(
        verbose_name=_("Details"),
        blank=True
    )

    order = models.PositiveSmallIntegerField(
        verbose_name=_("Order")
    )

    QUESTION_TYPES = Choices(
        (0, 'options', _('Options')),
        (1, 'text', _('Text')),
        (2, 'boolean', _('Yes/No')),
        (3, 'checkboxes', _('Checkboxes')),
    )

    type = models.PositiveSmallIntegerField(
        choices=QUESTION_TYPES,
        default=QUESTION_TYPES.options,
        verbose_name=_("Question Type")
    )

    exclude_from_score = models.BooleanField(
        default=False,
        verbose_name=_("Exclude from score")
    )

    class Meta:
        verbose_name = _("Acceptance Test Question")
        verbose_name_plural = _("Acceptance Test Questions")

    def __str__(self):
        return self.question

    def get_correct_answers(self):
        return self.acceptance_test_answers.filter(is_correct=True)

    def get_all_answers(self):
        return self.acceptance_test_answers.all()

    @property
    def score(self):
        if self.exclude_from_score: return 0

        answers = self.get_all_answers()

        if self.type == self.QUESTION_TYPES.text:
            return answers.first().score
        elif self.type == self.QUESTION_TYPES.boolean:
            return 5 if answers.first().is_correct else 1

        return answers.aggregate(score=models.Avg('score'))['score']


class AcceptanceTestAnswer(UUIDModel):
    acceptance_test_question = models.ForeignKey(
        AcceptanceTestQuestion,
        on_delete=models.CASCADE,
        related_name='acceptance_test_answers',
        verbose_name=_("Acceptance Test Question")
    )

    answer = models.CharField(
        max_length=255,
        verbose_name=_("Answer")
    )

    order = models.SmallIntegerField(
        verbose_name=_("Order")
    )

    is_correct = models.BooleanField(
        default=False,
        verbose_name=_("Is correct")
    )

    score = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Score"),
        help_text=_("Default score for Options type")
    )

    class Meta:
        verbose_name = _("Acceptance Test Answer")
        verbose_name_plural = _("Acceptance Test Answers")

    def __str__(self):
        return '{}: {}'.format(self.acceptance_test_question, self.answer)


class WorkflowObjectAnswer(UUIDModel):

    acceptance_test_question = models.ForeignKey(
        AcceptanceTestQuestion,
        on_delete=models.CASCADE,
        related_name='workflow_object_answers',
        verbose_name=_("Acceptance Test Question")
    )

    workflow_object = models.ForeignKey(
        WorkflowObject,
        on_delete=models.CASCADE,
        related_name='workflow_object_answers',
        verbose_name=_("Workflow Object")
    )

    answer = models.ForeignKey(
        AcceptanceTestAnswer,
        on_delete=models.CASCADE,
        related_name='workflow_object_answers',
        verbose_name=_("Acceptance Test Answer"),
        null=True,
        blank=True
    )

    answer_text = models.TextField(
        verbose_name=_("Text Answer"),
        null=True,
        blank=True
    )

    score = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Answer Score")
    )

    exclude = models.BooleanField(
        default=False,
        verbose_name=_("Exclude from score")
    )

    class Meta:
        verbose_name = _("Workflow Object Answer")
        verbose_name_plural = _("Workflow Object Answers")

    def __str__(self):
        return '{}, {}'.format(str(self.acceptance_test_question), str(self.workflow_object))

    def save(self, *args, **kwargs):
        if self.answer and self.answer.score != self.score:
            self.score = self.answer.score

        super().save(*args, **kwargs)

        is_all_test_filled = WorkflowObject.validate_tests(
            self.workflow_object.state, self.workflow_object.object_id, True, raise_exception=False
        )

        if is_all_test_filled:
            self.workflow_object.active = True
            self.workflow_object.save()


class AcceptanceTestRelationship(UUIDModel):

    acceptance_test = models.ForeignKey(
        AcceptanceTest,
        on_delete=models.CASCADE,
        related_name='acceptance_test_relations',
        verbose_name=_("Acceptance Test")
    )

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='acceptance_test_relations',
        verbose_name=_("Company")
    )

    class Meta:
        verbose_name = _("Acceptance Test Relation")
        verbose_name_plural = _("Acceptance Test Relations")

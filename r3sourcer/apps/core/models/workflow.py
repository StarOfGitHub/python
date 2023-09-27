from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from r3sourcer.apps.core.models import Company
from r3sourcer.helpers.models.abs import UUIDModel

__all__ = [
    'Workflow',
    'WorkflowNode',
    'WorkflowObject',
    'CompanyWorkflowNode',
]


class Workflow(UUIDModel):
    name = models.CharField(
        verbose_name=_('Name'),
        max_length=64
    )

    model = models.ForeignKey(
        ContentType,
        verbose_name=_('Binding model'),
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _('Workflow')
        verbose_name_plural = _('Workflows')

    def __str__(self):
        return self.name

    @classmethod
    def is_owned(cls):
        return False


class WorkflowNodeManager(models.Manager):

    def ordered(self):
        return self.get_queryset().order_by('order')

    def company(self, company):
        return self.get_queryset().filter(company=company)


class WorkflowNode(UUIDModel):
    workflow = models.ForeignKey(
        Workflow,
        related_name='nodes',
        on_delete=models.PROTECT,
        verbose_name=_('Workflow')
    )

    number = models.PositiveSmallIntegerField(
        verbose_name=_('State number')
    )

    full_path = models.CharField(
        max_length=32,
        editable=False,
        verbose_name=_('Full path')
    )

    name_before_activation = models.CharField(
        verbose_name=_('State name before activation'),
        max_length=128
    )

    name_after_activation = models.CharField(
        verbose_name=_('State name after activation'),
        max_length=128,
        null=True,
        blank=True
    )

    active = models.BooleanField(
        verbose_name=_('Active'),
        default=True
    )

    rules = JSONField(
        verbose_name=_('Rules'),
        null=True,
        blank=True
    )

    hardlock = models.BooleanField(
        verbose_name=_('Hardlock'),
        default=False
    )

    endpoint = models.CharField(
        verbose_name=_('Endpoint to activate state'),
        max_length=255,
        null=True,
        blank=True
    )

    initial = models.BooleanField(
        verbose_name=_('Is initial state'),
        default=False
    )

    parent = models.ForeignKey(
        'self',
        verbose_name=_('Parent Node'),
        null=True,
        blank=True,
        related_name='children',
        on_delete=models.CASCADE,
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_('Position')
    )

    objects = WorkflowNodeManager()

    class Meta:
        verbose_name = _('Workflow Node')
        verbose_name_plural = _('Workflow Nodes')

    def __str__(self):
        return '{} {}, {}'.format(self.full_path, self.workflow, self.name_before_activation)

    def save(self, *args, **kwargs):
        self.full_path = self.get_full_number()
        super().save(*args, **kwargs)

    @classmethod
    def validate_node(cls, number, workflow, company, active, rules, just_added, _id=None):
        system_state_qry = models.Q(workflow=workflow, number=number, hardlock=True)
        state_number_exist = WorkflowNode.objects.filter(
            system_state_qry |
            models.Q(workflow=workflow, number=number, company_workflow_nodes__company=company)
        )
        if not just_added:
            state_number_exist = state_number_exist.exclude(id=_id)

        if state_number_exist.exists():
            raise ValidationError(_('State with number {number} already exist on company').format(number=number))

        if not just_added:
            origin = WorkflowNode.objects.get(id=_id)
            number_changed = origin.number != number

            if number_changed:
                nodes = WorkflowNode.objects.filter(workflow=workflow, company_workflow_nodes__company=company)
                is_used = [
                    node.rules and str(origin.number) in node.get_rule_states()
                    for node in nodes
                ]
                if any(is_used):
                    raise ValidationError(
                        _("Number is used in other node's rules.")
                    )

    def get_rule_states(self):
        if self.rules and 'required_states' in self.rules:
            rule = self.rules['required_states']
            return str(self._get_state_from_rule(rule))\
                .replace('[', '').replace(']', '').replace(' ', '').split(',')
        return ''

    def _get_state_from_rule(self, rule):
        if isinstance(rule, list):
            return self._get_state_from_list(rule[1:])
        elif isinstance(rule, int):
            return rule

    def _get_state_from_list(self, rules):
        return [self._get_state_from_rule(rule) for rule in rules]

    @classmethod
    def get_company_nodes(cls, company, workflow, nodes=None):
        queryset = nodes or cls.objects

        return queryset.filter(
            company_workflow_nodes__company=company, active=True, company_workflow_nodes__active=True,
            workflow=workflow
        ).order_by('company_workflow_nodes__order', 'number').distinct()

    @classmethod
    def get_model_all_states(cls, model):
        states = cls.objects.filter(
            workflow__model=ContentType.objects.get_for_model(model)
        ).distinct('number').values(
            'number', 'name_before_activation', 'name_after_activation'
        )

        return [
            {'label': s['name_after_activation'] or s['name_before_activation'], 'value': s['number']} for s in states
        ]

    @classmethod
    def is_owned(cls):
        return False

    def get_full_number(self):
        if self.full_path:
            return self.full_path

        if self.parent is None:
            return str(self.number)

        return '{}.{}'.format(self.parent.full_path, self.number)


class WorkflowObject(UUIDModel):
    object_id = models.UUIDField(
        verbose_name=_('Object id'),
        help_text=_('ID of Object belonging to model in Workflow')
    )

    state = models.ForeignKey(
        WorkflowNode,
        verbose_name=_('State'),
        related_name='states',
        on_delete=models.CASCADE,
    )

    comment = models.TextField(
        verbose_name=_('Comments'),
        help_text=_('State Change Comment'),
        blank=True
    )

    active = models.BooleanField(
        verbose_name=_('Active'),
        default=True
    )

    score = models.SmallIntegerField(
        verbose_name=_('State score'),
        default=0
    )

    class Meta:
        verbose_name = _('Workflow object')
        verbose_name_plural = _('Workflow objects')

    def __str__(self):
        return str(self.state)

    @cached_property
    def model_object(self):
        return self.get_model_object(self.state, self.object_id)

    @classmethod
    def get_model_object(cls, state, object_id):
        result = None
        model = state.workflow.model.model_class()
        try:
            result = model.objects.get(id=object_id)
        except Exception:
            raise
        return result

    def save(self, *args, **kwargs):
        is_raw = kwargs.pop('raw', False)
        if not is_raw:
            self.clean()

        just_added = self._state.adding

        if just_added:
            if not is_raw:
                self.model_object.workflow(self.state)

        if just_added:
            self.model_object.after_state_created(self)

        if self.active:
            self.model_object.after_state_activated(self)
            self.model_object.active_true_workflow(self.state)

        super().save(*args, **kwargs)

    def clean(self):
        self.validate_object(self.state, self.object_id, self._state.adding)

    @classmethod
    def validate_object(cls, state, object_id, just_added):
        try:
            model_object = cls.get_model_object(state, object_id)
        except Exception as e:
            raise ValidationError(e)

        if not state.company_workflow_nodes.filter(company=model_object.get_closest_company()).exists():
            raise ValidationError(
                _('This state is not available for current object.')
            )

        if just_added and not model_object.is_allowed(state):
            raise ValidationError('{} {}'.format(
                _('State creation is not allowed.'),
                model_object.get_required_message(state))
            )

    @classmethod
    def validate_tests(cls, state, object_id, is_active, raise_exception=True):
        from r3sourcer.apps.acceptance_tests.models import AcceptanceTestWorkflowNode

        if not is_active:
            return

        try:
            model_object = cls.get_model_object(state, object_id)
        except Exception as e:
            raise ValidationError(e)

        qry = models.Q(
            acceptance_test__acceptance_tests_skills__isnull=True,
            acceptance_test__acceptance_tests_tags__isnull=True,
            acceptance_test__acceptance_tests_industries__isnull=True,
        )

        closest_company = model_object.get_closest_company()
        if closest_company.industries is not None:
            qry |= models.Q(acceptance_test__acceptance_tests_industries__industry__in=closest_company.industries.all())

        if hasattr(model_object, 'candidate_skills'):
            skill_ids = model_object.candidate_skills.values_list('skill', flat=True)
            qry |= models.Q(acceptance_test__acceptance_tests_skills__skill_id__in=skill_ids)

        if hasattr(model_object, 'tag_rels'):
            tag_ids = model_object.tag_rels.values_list('tag', flat=True)
            qry |= models.Q(acceptance_test__acceptance_tests_tags__tag_id__in=tag_ids)

        tests = AcceptanceTestWorkflowNode.objects.filter(
            qry, company_workflow_node__company=closest_company, company_workflow_node__workflow_node=state).distinct()
        is_answers_exist = tests.filter(
            acceptance_test__acceptance_test_questions__workflow_object_answers__workflow_object__object_id=object_id
        ).distinct().count() >= tests.count()

        return is_answers_exist

    def get_score(self, related_obj, company):
        from r3sourcer.apps.acceptance_tests.models import AcceptanceTestWorkflowNode

        children = self.state.children.filter(company_workflow_nodes__company=company).distinct()
        children_cnt = 0
        sub_score = 0

        if children.count() > 0:
            score_sum = 0

            for substate in children.all():
                child_wf_object = WorkflowObject.objects.filter(state=substate, object_id=related_obj.id).first()

                if not child_wf_object:
                    continue

                child_score = child_wf_object.get_score(related_obj, company)
                if child_score > 0:
                    score_sum += child_score
                    children_cnt += 1

            if score_sum > 0 and children_cnt > 0:
                sub_score = score_sum / children_cnt

        if self.score > 0:
            return (self.score + sub_score) / 2 if sub_score > 0 else self.score

        tests = AcceptanceTestWorkflowNode.objects.filter(company_workflow_node__workflow_node=self.state).distinct()
        a_tests = []
        for a_test in tests:
            a_score = a_test.get_score(self)
            if a_score > 0:
                a_tests.append(a_score)

        if sub_score > 0:
            a_tests.append(sub_score)

        score = sum(a_tests) / len(a_tests) if len(a_tests) > 0 else 0

        if score > 0:
            self.score = score
            self.save()
        else:
            score = self.score

        return score

    @classmethod
    def is_owned(cls):
        return False


class CompanyWorkflowNode(UUIDModel):
    company = models.ForeignKey(
        'core.Company',
        verbose_name=_('Company'),
        related_name='company_workflow_nodes',
        on_delete=models.CASCADE,
    )

    workflow_node = models.ForeignKey(
        WorkflowNode,
        verbose_name=_('Workflow Node'),
        related_name='company_workflow_nodes',
        on_delete=models.CASCADE,
    )

    active = models.BooleanField(
        default=True,
        verbose_name=_('Active')
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_('Order')
    )

    class Meta:
        verbose_name = _('Company Workflow Node')
        verbose_name_plural = _('Company Workflow Nodes')

    def __str__(self):
        return '{} {}'.format(self.company, self.workflow_node)

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                models.Q(company=owner),
                models.Q(company__regular_companies__master_company=owner)
            ]

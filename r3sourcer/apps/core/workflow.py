from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from django.db import models
from django.core.exceptions import ObjectDoesNotExist

from .mixins import CompanyLookupMixin
from .service import factory
from .utils.companies import get_site_master_company

NEED_REQUIREMENTS, ALLOWED, ACTIVE, VISITED, NOT_ALLOWED = range(5)


class WorkflowProcess(CompanyLookupMixin, models.Model):
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        is_fake = kwargs.pop('fake_wf', False)

        super(WorkflowProcess, self).__init__(*args, **kwargs)

        if not is_fake:
            try:
                self.active_states = self.get_active_states()
            except ObjectDoesNotExist:
                self.active_states = None

    @property
    def content_type(self):
        return ContentType.objects.get_for_model(self)

    def create_state(self, number, comment='', active=True):
        """
        Creates state by number
        :param number: int number of the state
        :param comment: str comment to state
        """
        from .models import WorkflowObject, WorkflowNode
        kwargs = {
            'number': number,
            'workflow__model': self.content_type,
            'company_workflow_nodes__company': self.get_closest_company(),
        }
        if not WorkflowNode.objects.filter(**kwargs).exists():
            kwargs['company_workflow_nodes__company'] = get_site_master_company()

        state = WorkflowNode.objects.filter(**kwargs).first()

        if state:
            workflow_object = WorkflowObject(object_id=self.id, state=state, comment=comment, active=active)
            workflow_object.save()

    def get_active_states(self):
        """
        Gets active states of the object
        :return: queryset of the states
        """
        from .models import WorkflowObject

        if not hasattr(self, 'id'):
            return WorkflowObject.objects.none()

        return WorkflowObject.objects.filter(
            object_id=self.id,
            state__workflow__model=self.content_type,
            state__company_workflow_nodes__company=self.get_closest_company(),
            active=True
        ).order_by('-state__number').distinct()

    def get_inactive_states(self):
        """
        Gets active states of the object
        :return: queryset of the states
        """
        from .models import WorkflowObject

        if not hasattr(self, 'id'):
            return WorkflowObject.objects.none()

        return WorkflowObject.objects.filter(
            object_id=self.id,
            state__workflow__model=self.content_type,
            state__company_workflow_nodes__company=self.get_closest_company(),
            active=False
        ).order_by('-state__number').distinct()

    def has_state(self, state, is_active=True):
        """
        Checks if object has state

        :param state: WorkflowNode or number
        :param is_active: Is existing state active?
        :return: True if state exists
        """
        from .models import WorkflowObject

        qry = models.Q(object_id=self.id, state__workflow__model=self.content_type)
        if isinstance(state, int):
            qry &= models.Q(state__number=state)
        else:
            qry &= models.Q(state=state)

        result = WorkflowObject.objects.filter(
            qry, state__company_workflow_nodes__company=self.get_closest_company()
        ).first()
        return result is not None

    def get_current_state(self):
        """
        Gets int value of the last state
        :return: last state
        """
        from .models import WorkflowObject
        try:
            result = WorkflowObject.objects.filter(
                object_id=self.id, state__workflow__model=self.content_type, active=True,
                state__company_workflow_nodes__company=self.get_closest_company()
            ).latest('created_at').state
        except (AttributeError, WorkflowObject.DoesNotExist):
            result = None
        return result

    def _get_rule_sign(self, rule):
        """
        Gets sign of the rule
        :return: str "or" or "and"
        """
        if len(rule) > 0:
            return rule[0]
        else:
            return "and"

    def _or_check(self, rules):
        """
        Checks rules via or operator
        :return: True or False
        """
        return any([self._check_condition(rule) for rule in rules])

    def _and_check(self, rules):
        """
        Checks rules via and operator
        :return: True or False
        """
        return all([self._check_condition(rule) for rule in rules])

    def _check_condition(self, rule):
        """
        Checks rule's type and selects check function for this type of rule
        """

        # TODO: add check that rule is formed properly
        if isinstance(rule, list):
            if len(rule) == 1:
                rule.insert(0, 'and')

            if self._get_rule_sign(rule) == "or":
                return self._or_check(rule[1:])
            else:
                return self._and_check(rule[1:])
        elif isinstance(rule, int):
            return self._check_state(rule)
        elif isinstance(rule, str):
            return self._check_function(rule)
        else:
            return True

    def _check_state(self, state):
        """
        Checks if state number is in active states of object
        :param state: int value of the state
        """
        return self.active_states.filter(state__number=state).exists()

    def _check_function(self, func):
        """
        Checks if object has passed function and it returns positive value
        :param func: str name of function
        """
        return hasattr(self, func) and getattr(self, func)()

    def is_allowed(self, new_state):
        """
        Checks if state is allowed for creation
        :param new_state: WorkflowNode value of new state
        :return: True or False
        """
        from .models import WorkflowNode, WorkflowObject
        if isinstance(new_state, int):
            new_state = WorkflowNode.objects.filter(
                workflow__model=ContentType.objects.get_for_model(self),
                number=new_state
            ).first()

        active_numbers = self.active_states.values_list(
            'state__number', flat=True
        )

        if new_state is None or new_state.number in active_numbers:
            return False

        result = True
        ns_rule = new_state.rules
        if ns_rule and "required_states" in ns_rule.keys():
            result = self._check_condition(ns_rule["required_states"])
        if ns_rule and "required_functions" in ns_rule.keys():
            result = result and self._check_condition(ns_rule["required_functions"])
        return result

    def _get_or_message(self, rules, new_state):
        return _(" or ").join([self._get_message_for_condition(rule, new_state) for rule in rules
                               if self._get_message_for_condition(rule, new_state)])

    def _get_and_message(self, rules, new_state):
        return _(" and ").join([self._get_message_for_condition(rule, new_state) for rule in rules
                                if self._get_message_for_condition(rule, new_state)])

    def _get_message_for_condition(self, rule, new_state):
        """
        Checks rule's type and selects message for this type of rule
        """
        message = ""
        if isinstance(rule, list):
            if len(rule) == 1:
                rule.insert(0, 'and')

            if self._get_rule_sign(rule) == "or":
                return self._get_or_message(rule[1:], new_state)
            else:
                return self._get_and_message(rule[1:], new_state)
        elif isinstance(rule, int):
            if not self._check_state(rule):
                message = self._get_state_name(rule)
        else:
            if not self._check_function(rule):
                message = self._get_function_name(rule)
        return message

    def _get_function_name(self, func):
        try:
            return str(getattr(getattr(self, func), 'short_description'))
        except Exception:
            return str(func)

    def _get_state_name(self, state_number):
        from .models.workflow import WorkflowNode

        if WorkflowNode.objects.filter(
                workflow__model=self.content_type, number=state_number).exists():
            return WorkflowNode.objects \
                .filter(workflow__model=self.content_type, number=state_number) \
                .first().name_before_activation
        else:
            return str(state_number)

    def get_required_messages(self, new_state, require_states=True):
        """
        Get list of messages with requirements for new state
        :param new_state: new state
        :return: list of messages with requirements
        """
        messages = []
        self.active_states = self.get_active_states()

        if self.active_states.filter(state=new_state).exists():
            messages = [_("State is already active")]
        elif new_state.rules:
            ns_rule = new_state.rules
            checks = ['required_functions']
            if require_states:
                checks.append('required_states')
            for requirement in checks:
                if requirement in ns_rule.keys():
                    part = self._get_message_for_condition(
                        ns_rule[requirement], new_state)
                    if not part:
                        continue

                    verb = _("are") \
                        if " or " in part or " and " in part else _("is")
                    messages.append(_("{} {} required.").format(
                        part, verb
                    ))

        return messages

    def get_required_message(self, new_state):
        """
        Get message with requirements for new state
        :param new_state: new state
        :return: message with requirements
        """
        return ''.join(
            [str(item) for item in self.get_required_messages(new_state)]
        )

    def active_false_workflow(self, state):
        states = self.get_inactive_states()
        rules = state.rules
        if not rules:
            return

        if 'inactive' in rules.keys():
            for state in states:
                if state.state.number in rules["inactive"]:
                    state.active = True
                    state.save(update_fields=['active'])

    def active_true_workflow(self, state):
        states = self.get_active_states()
        rules = state.rules
        if not rules:
            return

        if 'active' in rules.keys():
            for state in states:
                if state.state.number not in rules["active"]:
                    state.active = False
                    state.save(update_fields=['active'])

    def workflow(self, new_state):
        """
        Process the workflow: set active states and execute 'actions'
        :param new_state: new state
        """
        self.active_states = self.get_active_states()
        if new_state.rules:
            ns_rule = new_state.rules

            if 'active' in ns_rule.keys():
                for astate in self.active_states:
                    if astate.state.number not in ns_rule["active"]:
                        astate.active = False
                        astate.save(update_fields=['active'])

            if 'actions' in ns_rule.keys():
                for action in ns_rule["actions"]:
                    if hasattr(self, action):
                        getattr(self, action)()

    def get_available_states_for_creation(self):
        """
        Gets array of the available states for creation
        :return: array of the available WorkflowNodes
        """
        available_states = []
        self.active_states = self.get_active_states()

        from .models.workflow import WorkflowNode

        self_nodes = self._get_companies_nodes(self.get_closest_company())
        default_nodes = self._get_companies_nodes(get_site_master_company())

        all_nodes = list(self_nodes.values())
        all_nodes.extend(value for key, value in default_nodes.items() if key not in self_nodes.keys())

        for state in WorkflowNode.objects.filter(id__in=all_nodes):
            if not self.active_states.filter(state=state).exists() and self.is_allowed(state):
                available_states.append(state)
        return available_states

    def _get_companies_nodes(self, company):

        from .models.workflow import WorkflowNode
        nodes = {}
        for node in WorkflowNode.objects.filter(
            workflow__model=self.content_type,
            company_workflow_nodes__company=company
        ).order_by('number'):
            nodes[node.number] = node.id
        return nodes

    def before_state_creation(self, workflow_object):
        """
        Lifecycle callback: before some state created

        :param state: WorkflowObject instance
        """
        pass

    def after_state_created(self, workflow_object):
        """
        Lifecycle callback: after some state created

        :param state: WorkflowObject instance
        """
        pass

    def after_state_activated(self, workflow_object):
        """
        Lifecycle callback: after some state activated

        :param state: WorkflowObject instance
        """
        pass


class CompanyRelState60:
    def check(self, obj):
        return obj.is_business_id_set()


class OrderState50:
    def check(self, obj):
        return True


class OrderState90:
    def check(self, obj):
        return True


factory.register('company_state_60', CompanyRelState60)
factory.register('order_state_50', OrderState50)
factory.register('order_state_90', OrderState90)

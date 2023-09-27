from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django_filters import NumberFilter

from crum import get_current_request
from rest_framework import exceptions

from r3sourcer.apps.logger.main import endless_logger
from r3sourcer.apps.core.models import User, WorkflowObject, WorkflowNode
from r3sourcer.apps.core.utils.address import parse_google_address
from r3sourcer.apps.core.utils.companies import get_site_master_company


class WorkflowStatesColumnMixin():

    def get_method_fields(self):
        method_fields = list(super().get_method_fields())
        return method_fields + ['active_states']

    def get_active_states(self, obj):
        if not obj:
            return

        states = obj.get_active_states()

        return [
            {
                '__str__': state.state.name_after_activation or state.state.name_before_activation,
                'number': state.state.number,
                'id': state.state.id,
            } for state in states
        ]


class CreatedUpdatedByMixin:

    def get_method_fields(self):
        method_fields = list(super().get_method_fields())
        return method_fields + ['created_by', 'updated_by']

    def get_field_to_check_create(self, obj):
        return 'id'

    def get_field_to_check_update(self, obj):
        return 'updated_at'

    def _get_log_updated_by(self, obj, log_type=None):
        if log_type and log_type == 'create':
            field = self.get_field_to_check_create(obj)
        else:
            field = self.get_field_to_check_update(obj)

        log_entry = endless_logger.get_recent_field_change(self.Meta.model, obj.id, field, log_type)
        if 'updated_by' in log_entry:
            user = User.objects.get(id=log_entry['updated_by'])
            email = user.email if hasattr(user, 'contact') else None
        else:
            email = None

        if not email:
            email = settings.SYSTEM_USER

        return email

    def get_created_by(self, obj):
        return self._get_log_updated_by(obj, 'create')

    def get_updated_by(self, obj):
        return self._get_log_updated_by(obj)


class ActiveStateFilterMixin:

    active_states = NumberFilter(method='filter_active_state')

    def _get_closest_company(self):
        current_request = get_current_request()

        if current_request:
            current_user = current_request.user
            if current_user.contact.is_company_contact():
                current_company = current_user.contact.get_closest_company()
                return current_company

        return get_site_master_company(request=current_request)

    def _fetch_workflow_objects(self, value):  # pragma: no cover
        content_type = ContentType.objects.get_for_model(self.Meta.model)
        wf_node_order = WorkflowNode.objects.get(number=value, workflow__model=content_type, active=True).order

        objects = WorkflowObject.objects.filter(
            Q(
                Q(state__number__gt=value) | Q(state__order__gt=wf_node_order),
                state__workflow__model=content_type,
                state__company_workflow_nodes__company=self._get_closest_company(),
                active=True
            ) |
            Q(state__workflow__isnull=True)
        ).distinct('object_id').values_list('object_id', flat=True)

        return WorkflowObject.objects.exclude(object_id__in=objects).filter(
            state__number=value,
            state__workflow__model=content_type,
            state__company_workflow_nodes__company=self._get_closest_company(),
            active=True
        ).distinct('object_id').values_list('object_id', flat=True)

    def filter_active_state(self, queryset, name, value):
        objects = self._fetch_workflow_objects(value)
        return queryset.filter(id__in=objects)


class GoogleAddressMixin:

    raise_invalid_address = True
    root_address = False

    def prepare_related_data(self, data, is_create=False):
        data = super().prepare_related_data(data, is_create)
        if data.get('address', data.get('street_address')) is None:
            return data

        if (not self.root_address and 'address' not in data) or (self.root_address and 'street_address' not in data):
            return data

        address_data = data['street_address'] if self.root_address else data['address']

        if not is_create and 'address_components' not in address_data:
            return data

        try:
            data['address'] = parse_google_address(address_data)
        except Exception as e:
            if self.raise_invalid_address:
                raise exceptions.ValidationError({'address': _('Please enter valid address!')})
            else:
                data['address'] = None

        return data['address'] if self.root_address else data


class WorkflowLatestStateMixin:

    def get_method_fields(self):
        method_fields = list(super().get_method_fields())
        return method_fields + ['latest_state']

    def get_latest_state(self, obj):
        if not obj:
            return []

        state = obj.get_active_states().first()

        return [{
            '__str__': state.state.name_after_activation or state.state.name_before_activation,
            'number': state.state.number,
            'id': state.state.id,
        }] if state else []


class ApiContentTypeFieldMixin:

    def get_method_fields(self):
        method_fields = list(super().get_method_fields())
        return method_fields + ['model_content_type']

    def get_model_content_type(self, obj):
        if not obj:
            return None

        return ContentType.objects.get_for_model(self.Meta.model).pk

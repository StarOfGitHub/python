import json

from django.forms.utils import flatatt
from django.utils.html import format_html
from mptt.admin import DraggableMPTTAdmin


class RelatedFieldMixin(object):
    """
    Provides related fields which will be used in the queryset
    """
    ct_field = "content_type"
    ct_fk_field = "object_id"


class ExtendedDraggableMPTTAdmin(DraggableMPTTAdmin):

    def changelist_view(self, request, *args, **kwargs):
        response = super(ExtendedDraggableMPTTAdmin, self).changelist_view(request, *args, **kwargs)
        response.context_data['mptt_extra_data'] = format_html('{0}', flatatt({
            'id': 'draggable-admin-context',
            'data-context': json.dumps(self._tree_context(request)),
        }))
        return response

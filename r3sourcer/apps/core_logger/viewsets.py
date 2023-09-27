from django.apps import apps
from django.utils.translation import ugettext_lazy as _

from rest_framework.exceptions import ParseError

from r3sourcer.apps.core.api.viewsets import BaseApiViewset
from r3sourcer.apps.logger.main import endless_logger


class LoggerViewset(BaseApiViewset):

    @classmethod
    def get_logs(cls, model, obj_id=None):
        logs = []
        res = endless_logger.get_object_history(model)

        for i, change in enumerate(res):
            if obj_id and change.get('object_id') != obj_id:
                continue

            keys = set(change.keys()) - {'by', 'diff'}
            logs.append({
                'id': i,
                'by': change['by']['name'],
                'model': '%s.%s' % (model._meta.app_label,
                                    model._meta.object_name),
                **{key: change[key] for key in keys}
            })

        return logs

    def get_queryset(self):
        model = self.request.query_params.get('model', '.')
        obj_id = self.request.query_params.get('obj_id')

        try:
            retrieving_model = apps.get_model(*model.split('.'))
        except (LookupError, ValueError):
            raise ParseError(_("'model' query parameter not found"))

        return self.get_logs(retrieving_model, obj_id)


class LoggerDiffViewset(BaseApiViewset):

    def list(self, request, *args, **kwargs):
        self.model = kwargs.pop('model')
        self.obj_id = kwargs.pop('obj_id')

        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        timestamp = self.request.query_params.get('timestamp')
        if not timestamp:
            raise ParseError(_("'timestamp' is not set"))

        try:
            retrieving_model = apps.get_model(*self.model.split('.'))
        except (LookupError, ValueError):
            raise ParseError(_("%(model)s not found") % {'model': self.model})

        res = endless_logger.get_object_changes(
            retrieving_model, self.obj_id, timestamp
        )
        res = res.get('fields', [])
        for i, change in enumerate(res):
            change['id'] = i
        return res

import mock

from django.apps import apps

from r3sourcer.apps.core_logger.endpoints import LoggerEndpoint, LoggerDiffEndpoint
from r3sourcer.apps.core_logger.models import LoggerModel, LoggerDiffModel

from r3sourcer.apps.logger.main import endless_logger


LoggerViewset = LoggerEndpoint().get_viewset()
LoggerDiffViewset = LoggerDiffEndpoint().get_viewset()


class TestLoggerViewset:

    def get_response_as_view(self, request):
        kwargs = {'request': request}
        viewset = LoggerViewset
        view = viewset.as_view({'get': 'list'})
        response = view(**kwargs)
        response.render()
        return response

    @mock.patch.object(endless_logger, 'get_object_history')
    def test_get_logs(self, mock_obj_hist):
        mock_obj_hist.return_value = [{
            'at': 'test',
            'by': {'name': 'name'},
            'diff': []
        }]

        logs = LoggerViewset.get_logs(LoggerModel)

        assert len(logs) == 1
        assert logs[0]['by'] == 'name'
        assert 'diff' not in logs[0]

    @mock.patch.object(endless_logger, 'get_object_history')
    def test_get_logs_empty(self, mock_obj_hist):
        mock_obj_hist.return_value = []

        logs = LoggerViewset.get_logs(LoggerModel)

        assert len(logs) == 0

    @mock.patch.object(endless_logger, 'get_object_history')
    def test_get_logs_object_id(self, mock_obj_hist):
        mock_obj_hist.return_value = [{
            'at': 'test',
            'by': {'name': 'name'},
            'object_id': '1',
        }]

        logs = LoggerViewset.get_logs(LoggerModel, '1')

        assert len(logs) == 1

    @mock.patch.object(endless_logger, 'get_object_history')
    def test_get_logs_object_id_not_found(self, mock_obj_hist):
        mock_obj_hist.return_value = [{
            'at': 'test',
            'by': {'name': 'name'},
            'object_id': '1',
        }]

        logs = LoggerViewset.get_logs(LoggerModel, '0')

        assert len(logs) == 0

    @mock.patch.object(endless_logger, 'get_object_history')
    def test_get_logs_without_object_id(self, mock_obj_hist):
        mock_obj_hist.return_value = [{
            'at': 'test',
            'by': {'name': 'name'}
        }]

        logs = LoggerViewset.get_logs(LoggerModel, '0')

        assert len(logs) == 0

    @mock.patch.object(apps, 'get_model')
    @mock.patch.object(LoggerViewset, 'get_logs')
    def test_get_queryset(self, mock_obj_hist, mock_get_model, rf):
        mock_obj_hist.return_value = [{
            'at': 'test',
            'by': 'name',
            'model': 'model',
            'id': 0,
            'transaction_type': 'type',
            'timestamp': '1',
        }]
        mock_get_model.return_value = LoggerModel

        req = rf.get('/log/?model=model.test&obj_id=obj_id')
        resp = self.get_response_as_view(req)

        assert resp.data['count'] == 1

    @mock.patch.object(LoggerViewset, 'get_logs')
    def test_get_queryset_model_not_found(self, mock_obj_hist, rf):
        mock_obj_hist.return_value = [{
            'at': 'test',
            'by': 'name',
            'model': 'model',
        }]

        req = rf.get('/log/?model=model.test&obj_id=obj_id')
        resp = self.get_response_as_view(req)

        assert resp.status_code == 400

    @mock.patch.object(LoggerViewset, 'get_logs')
    def test_get_queryset_model_wrong_format(self, mock_obj_hist, rf):
        mock_obj_hist.return_value = [{
            'at': 'test',
            'by': 'name',
            'model': 'model',
        }]

        req = rf.get('/log/?model=model.test&obj_id=obj_id')
        resp = self.get_response_as_view(req)

        assert resp.status_code == 400


class TestLoggerDiffViewset:

    def get_response_as_view(self, request, **kwargs):
        kwargs['request'] = request
        viewset = LoggerDiffViewset
        view = viewset.as_view({'get': 'list'})
        response = view(**kwargs)
        response.render()
        return response

    @mock.patch.object(apps, 'get_model')
    @mock.patch.object(endless_logger, 'get_object_changes')
    def test_get_queryset(self, mock_obj_changes, mock_get_model, rf):
        mock_obj_changes.return_value = {
            'fields': [{
                'id': 0,
                'field': 'field',
                'new_value': 'new',
                'old_value': 'old',
            }]
        }
        mock_get_model.return_value = LoggerDiffModel

        req = rf.get('/log/?timestamp=1')
        resp = self.get_response_as_view(req, model='model.test',
                                         obj_id='obj_id')

        assert resp.data['count'] == 1

    def test_get_queryset_no_timestamp(self, rf):
        req = rf.get('/log/')
        resp = self.get_response_as_view(req, model='model', obj_id='obj_id')

        assert resp.status_code == 400

    @mock.patch.object(endless_logger, 'get_object_changes')
    def test_get_queryset_model_not_found(self, mock_obj_changes, rf):
        mock_obj_changes.return_value = {
            'fields': [{
                'id': 0,
                'field': 'field',
                'new_value': 'new',
                'old_value': 'old',
            }]
        }

        req = rf.get('/log/?timestamp=1')
        resp = self.get_response_as_view(req, model='model.test',
                                         obj_id='obj_id')

        assert resp.status_code == 400

    def test_get_queryset_model_wrong_format(self, rf):
        req = rf.get('/log/?timestamp=1')
        resp = self.get_response_as_view(req, model='model', obj_id='obj_id')

        assert resp.status_code == 400

import mock
import pytest

from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from r3sourcer.apps.core_logger.endpoints import log, LoggerEndpoint
from r3sourcer.apps.core_logger.viewsets import LoggerViewset

from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.core.models import Company


class ApiTestEndpoint(ApiEndpoint):
    model = Company


class TestLog:

    @mock.patch.object(LoggerViewset, 'get_logs')
    def test_log(self, mock_logs, rf):
        mock_logs.return_value = [{
            'at': 'test',
            'by': 'name',
            'model': 'model',
        }]

        obj = mock.MagicMock()
        obj.get_serializer_class.return_value = ApiTestEndpoint().get_serializer()
        obj.get_paginated_response.return_value = Response({
            'count': 1,
            'results': mock_logs(),
        })

        req = rf.get('/log/')

        resp = log(obj, req)

        assert resp.data['count'] == 1

    @mock.patch.object(LoggerViewset, 'get_logs')
    def test_log_logger_disabled(self, mock_logs, rf):
        mock_logs.return_value = [{
            'at': 'test',
            'by': 'name',
            'model': 'model',
        }]

        obj = mock.MagicMock()
        obj.get_serializer_class.return_value = LoggerEndpoint().get_serializer()

        req = rf.get('/log/')

        with pytest.raises(NotFound):
            log(obj, req)

    @mock.patch.object(LoggerViewset, 'get_logs')
    def test_log_without_pagination(self, mock_logs, rf):
        mock_logs.return_value = [{
            'at': 'test',
            'by': 'name',
            'model': 'model',
        }]

        obj = mock.MagicMock()
        obj.get_serializer_class.return_value = ApiTestEndpoint().get_serializer()
        obj.paginate_queryset.return_value = None

        req = rf.get('/log/')

        resp = log(obj, req)

        assert len(resp.data) == 1

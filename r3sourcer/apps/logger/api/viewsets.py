import datetime

from django.apps import apps
from django.conf import settings
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from ..main import endless_logger


class LogHistoryViewset(viewsets.ViewSet):
    http_method_names = ['get', 'options']

    def _get_kwargs(self, request):
        from_date = request.query_params.get("from", None)
        to_date = request.query_params.get("to", None)
        page = request.query_params.get("page", None)
        length = request.query_params.get("length", settings.REST_FRAMEWORK.get('PAGE_SIZE', 250))

        if from_date and isinstance(from_date, str):
            try:
                from_date = datetime.datetime.strptime(from_date, '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                raise APIException(e)

        if to_date and isinstance(to_date, str):
            try:
                to_date = datetime.datetime.strptime(to_date, '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                raise APIException(e)

        kwargs = {"from_date": from_date, "to_date": to_date}
        if page:
            try:
                page = int(page)
            except ValueError:
                page = 1
            else:
                if page <= 0:
                    page = 1
            try:
                length = int(length)
            except ValueError:
                length = settings.REST_FRAMEWORK.get('PAGE_SIZE', 250)

            kwargs["offset"] = (page - 1) * length
            kwargs["limit"] = length
        return kwargs

    def list(self, request,  *args, **kwargs):
        app_path = kwargs.get('app_path', None)
        model = kwargs.get('model', None)

        if app_path and model:
            try:
                retrieving_model = apps.get_model(app_path, model)
            except LookupError as e:
                raise APIException(e)
            else:
                log_kwargs = self._get_kwargs(request)
                history = endless_logger.get_object_history(retrieving_model, **log_kwargs)
                log_kwargs.pop("limit", 250)
                log_kwargs.pop("offset", 0)
                total = endless_logger.get_result_length(retrieving_model, **log_kwargs)
                return Response({"recordsTotal": total, "recordsFiltered": total, "data": history})
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None, *args, **kwargs):
        app_path = kwargs.get('app_path', None)
        model = kwargs.get('model', None)
        if app_path and model:
            try:
                retrieving_model = apps.get_model(app_path, model)
            except LookupError as e:
                raise APIException(e)
            else:
                log_kwargs = self._get_kwargs(request)
                history = endless_logger.get_object_history(retrieving_model, pk, **log_kwargs)
                log_kwargs.pop("limit", 250)
                log_kwargs.pop("offset", 0)
                total = endless_logger.get_result_length(retrieving_model, **log_kwargs)
                return Response({"recordsTotal": total, "recordsFiltered": total, "data": history})
        return Response(status=status.HTTP_400_BAD_REQUEST)


journal_list = LogHistoryViewset.as_view({'get': 'list'})
journal_detail = LogHistoryViewset.as_view({'get': 'retrieve'})

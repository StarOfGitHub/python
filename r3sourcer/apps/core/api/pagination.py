from collections import OrderedDict

from rest_framework.pagination import LimitOffsetPagination, _positive_int
from rest_framework.response import Response


class ApiLimitOffsetPagination(LimitOffsetPagination):

    def get_limit(self, request):
        if self.limit_query_param:
            try:
                limit = int(request.query_params[self.limit_query_param])
                if limit < 0:
                    return self.count
                return _positive_int(
                    limit,
                    strict=True,
                    cutoff=self.max_limit
                )
            except (KeyError, ValueError):
                pass

        return self.default_limit

    def get_offset(self, request):
        return super(ApiLimitOffsetPagination, self).get_offset(request)

    def get_paginated_response(self, data):
        message = None
        results = data
        if isinstance(data, dict):
            message = data.pop('message', None)
            results = data.get('results')
        return Response(OrderedDict([
            ('count', self.count),
            ('message', message),
            ('results', results)
        ]))

    def paginate_queryset(self, queryset, request, view=None):
        if not queryset.query.order_by:
            queryset = queryset.order_by('pk')

        return super().paginate_queryset(queryset, request, view)

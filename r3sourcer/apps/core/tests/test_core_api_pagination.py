import pytest

from django_mock_queries.query import MockSet, MockModel
from rest_framework.request import Request

from r3sourcer.apps.core.api.pagination import ApiLimitOffsetPagination


class TestApiLimitOffsetPagination:

    @pytest.fixture
    def paginator(self, rf):
        req = rf.get('/')
        pagination = ApiLimitOffsetPagination()

        qs = MockSet(
            MockModel(id=1),
            MockModel(id=2)
        )
        pagination.paginate_queryset(qs, Request(req))

        return pagination

    def test_response_list(self, paginator):
        response = paginator.get_paginated_response([
            {
                'test': 'test',
            }
        ])

        assert 'test' in response.data['results'][0]

    def test_response_dist(self, paginator):
        response = paginator.get_paginated_response(
            {
                'results': [],
                'message': 'test'
            }
        )

        assert response.data['message'] == 'test'

    def test_get_limit(self, paginator, rf):
        req = rf.get('/')
        paginator.limit_query_param = None

        assert paginator.get_limit(req) == paginator.default_limit

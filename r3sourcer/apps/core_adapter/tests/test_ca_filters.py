import mock

from django_mock_queries.query import MockModel, MockSet
from r3sourcer.apps.core_adapter.filters import ValuesFilter


class TestValuesFilter:

    def test_field(self):
        qs = mock.MagicMock()
        type(qs)._default_manager = mock.PropertyMock(
            return_value=MockSet(MockModel(test='1'))
        )

        filter_field = ValuesFilter(name='test')
        filter_field.model = qs
        filter_field.field

        assert filter_field.extra['choices'] == [('1', '1')]

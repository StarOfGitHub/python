import mock
import pytest

from r3sourcer.apps.pricing.api.serializers import (
    DynamicCoefficientRuleSerializer, RateCoefficientSerializer
)
from r3sourcer.apps.pricing.models import DynamicCoefficientRule


@pytest.mark.django_db
class TestDynamicCoefficientRuleSerializer:

    @pytest.fixture
    def dynamic_rule(self, rate_coefficient, monday_rule):
        return DynamicCoefficientRule.objects.create(
            rate_coefficient=rate_coefficient,
            rule=monday_rule,
        )

    @pytest.fixture
    def serializer(self):
        return DynamicCoefficientRuleSerializer()

    def test_get_rule(self, serializer, dynamic_rule):
        res = serializer.get_rule(dynamic_rule)

        assert res == 'Rule for: mon'

    def test_get_rule_none(self, serializer):
        res = serializer.get_rule(None)

        assert res is None

    def test_get_rule_endpoint_none(self, serializer):
        res = serializer.get_rule_endpoint(None)

        assert res is None

    @mock.patch('r3sourcer.apps.pricing.api.serializers.api_reverse_lazy',
                return_value='endpoint')
    def test_get_rule_endpoint(self, mock_reverse, serializer, dynamic_rule):
        res = serializer.get_rule_endpoint(dynamic_rule)

        assert res == 'endpoint'


@pytest.mark.django_db
class TestRateCoefficientSerializer:

    @pytest.fixture
    def dynamic_rule(self, rate_coefficient, monday_rule):
        return DynamicCoefficientRule.objects.create(
            rate_coefficient=rate_coefficient,
            rule=monday_rule,
            used=True,
        )

    @pytest.fixture
    def serializer(self):
        return RateCoefficientSerializer()

    def test_get_rule(self, serializer, rate_coefficient, dynamic_rule):
        res = serializer.get_rules(rate_coefficient)

        assert len(res) == 1

    def test_get_rule_none(self, serializer):
        res = serializer.get_rules(None)

        assert res == []

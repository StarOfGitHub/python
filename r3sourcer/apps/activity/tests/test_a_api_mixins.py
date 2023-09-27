import datetime

import freezegun
import mock
import pytest

from r3sourcer.apps.activity.api import mixins as activity_mixins


@pytest.mark.django_db
class TestRelatedActivitiesColumnMixin:

    @pytest.fixture
    def obj(self):
        return activity_mixins.RelatedActivitiesColumnMixin()

    @mock.patch.object(
        activity_mixins.RelatedActivitiesColumnMixin, 'get_related_activities', return_value=(1, 2, 3)
    )
    def test_get_actual_activities(self, mock_related, obj):
        assert obj.get_actual_activities(obj) == 2

    @mock.patch.object(
        activity_mixins.RelatedActivitiesColumnMixin, 'get_related_activities', return_value=None
    )
    def test_get_actual_activities_none(self, mock_related, obj):
        assert obj.get_actual_activities(obj) is None

    @mock.patch.object(
        activity_mixins.RelatedActivitiesColumnMixin, 'get_related_activities', return_value=(1, 2, 3)
    )
    def test_get_overdue_activities(self, mock_related, obj):
        assert obj.get_overdue_activities(obj) == 3

    @mock.patch.object(
        activity_mixins.RelatedActivitiesColumnMixin, 'get_related_activities', return_value=None
    )
    def test_get_overdue_activities_none(self, mock_related, obj):
        assert obj.get_overdue_activities(obj) == '-'

    @mock.patch.object(
        activity_mixins.RelatedActivitiesColumnMixin, 'get_related_activities', return_value=(1, 2, 3)
    )
    def test_get_total_activities(self, mock_related, obj):
        assert obj.get_total_activities(obj) == 1

    @mock.patch.object(
        activity_mixins.RelatedActivitiesColumnMixin, 'get_related_activities', return_value=None
    )
    def test_get_total_activities_none(self, mock_related, obj):
        assert obj.get_total_activities(obj) is None

    def test_get_related_activities_obj_none(self, obj):
        assert obj.get_related_activities(None) is None

    @freezegun.freeze_time(datetime.date(2017, 1, 5))
    @mock.patch('r3sourcer.apps.activity.api.mixins.cache')
    def test_get_related_activities(self, mock_cache, obj, related_activity, primary_user):
        res = obj.get_related_activities(primary_user)

        assert res == (1, 1, 0)

    @freezegun.freeze_time(datetime.date(2017, 1, 13))
    @mock.patch('r3sourcer.apps.activity.api.mixins.cache')
    def test_get_related_activities_overdue(self, mock_cache, obj, related_activity, primary_user):
        res = obj.get_related_activities(primary_user)

        assert res == (1, 0, 1)

    @mock.patch('r3sourcer.apps.activity.api.mixins.cache')
    def test_get_related_activities_cached(self, mock_cache, obj):
        mock_cache.get.return_value = (1, 2, 3)

        obj.id = 1
        res = obj.get_related_activities(obj)

        assert res == (1, 2, 3)

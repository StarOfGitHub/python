from django_filters.filters import ChoiceFilter, DateFromToRangeFilter, DateTimeFromToRangeFilter, RangeFilter


class DistinctFilterMixin:

    def filter(self, qs, value):
        qs = super().filter(qs, value)
        if self.distinct:
            qs = qs.distinct()

        return qs


class ValuesFilter(ChoiceFilter):
    @property
    def field(self):
        qs = self.model._default_manager
        qs = qs.order_by(self.name).values_list(
            self.name, flat=True
        ).distinct()
        self.extra['choices'] = [(o, o) for o in qs]
        return super(ValuesFilter, self).field


class RangeNumberFilter(RangeFilter):

    def filter(self, qs, value):
        if value:
            if value.start is not None:
                qs = self.get_method(qs)(**{'%s__gte' % self.field_name: value.start})
            if value.stop is not None:
                qs = self.get_method(qs)(**{'%s__lte' % self.field_name: value.stop})

            if self.distinct:
                qs = qs.distinct()
        return qs


class DateRangeFilter(DistinctFilterMixin, DateFromToRangeFilter):
    pass


class DateTimeRangeFilter(DistinctFilterMixin, DateTimeFromToRangeFilter):
    pass

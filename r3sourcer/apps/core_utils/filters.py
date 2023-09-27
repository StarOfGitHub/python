from datetime import timedelta
from urllib import parse as urllib_parse

from django.contrib import admin
from django.contrib.admin.filters import (
    AllValuesFieldListFilter, RelatedFieldListFilter
)
from django.contrib.admin.utils import get_model_from_relation

from django.db.models import DateTimeField
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _

from .forms import DateCondRangeForm
from ...helpers.datetimes import utc_now


class DateRangesMixin(object):

    SHORTCUTS = ['last_week', 'this_week', 'yesterday', 'today', 'tomorrow', 'next_week']
    DEFAULT_SHORTCUTS = ['yesterday', 'today', 'tomorrow']

    def __init__(self, *args, **kwargs):
        super(DateRangesMixin, self).__init__(*args, **kwargs)
        self.model_admin = args[4]
        self.extra_data_fields = self.get_data_ranges_initial()

    def get_range_fields(self):
        if isinstance(self, DatePeriodRangeAdminFilter):
            return [self.lookup_gte_kwarg, self.lookup_lte_kwarg]
        raise NotImplemented

    def get_ranges_query(self, extra_dict):
        return urllib_parse.urlencode(extra_dict)

    def get_data_ranges_initial(self):
        today = utc_now().date()
        monday = (today - timedelta(days=today.weekday()))
        sunday = (today + timedelta(days=(6 - today.weekday())))
        last_monday = monday - timedelta(days=7)
        last_sunday = sunday - timedelta(days=7)
        next_monday = monday + timedelta(days=7)
        next_sunday = sunday + timedelta(days=7)

        yesterday_str = date_format(today - timedelta(days=1))
        tomorrow_str = date_format(today + timedelta(days=1))
        today_str = date_format(today)
        last_monday_str = date_format(last_monday)
        last_sunday_str = date_format(last_sunday)
        current_monday_str = date_format(monday)
        current_sunday_str = date_format(sunday)
        next_monday_str = date_format(next_monday)
        next_sunday_str = date_format(next_sunday)

        gte, lte = self.get_range_fields()

        dates = {
            'last_week': (_("Last week"), self.get_ranges_query({gte: last_monday_str, lte: last_sunday_str})),
            'this_week': (_("This week"), self.get_ranges_query({gte: current_monday_str, lte: current_sunday_str})),
            'yesterday': (_("Yesterday"), self.get_ranges_query({gte: yesterday_str, lte: yesterday_str})),
            'today': (_("Today"), self.get_ranges_query({gte: today_str, lte: today_str})),
            'tomorrow': (_("Tomorrow"), self.get_ranges_query({gte: tomorrow_str, lte: tomorrow_str})),
            'next_week': (_("Next week"), self.get_ranges_query({gte: next_monday_str, lte: next_sunday_str}))

        }

        return [dates.get(dt_shortcut) for dt_shortcut in self.DEFAULT_SHORTCUTS if dt_shortcut in dates]


class DatePeriodRangeAdminFilter(DateRangesMixin, admin.filters.FieldListFilter):
    template = 'admin/date_period_range_filter.html'

    suffix = ''

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.lookup_field = field_path

        if isinstance(field, DateTimeField):
            self.suffix = '__date'

        self.lookup_lte_kwarg = '%s%s__lte' % (field_path, self.suffix)
        self.lookup_gte_kwarg = '%s%s__gte' % (field_path, self.suffix)

        super(DatePeriodRangeAdminFilter, self).__init__(
            field, request, params, model, model_admin, field_path)
        self.form = self.get_form(request)

    def get_form(self, request):
        return DateCondRangeForm(request, field_name=self.lookup_field,
                                 data=request.GET, suffix=self.suffix)

    def choices(self, cl):
        """
        Pop the original parameters, and return the date filter & other filter
        parameters.
        """
        params = cl.params.copy()
        params.pop(self.lookup_lte_kwarg, None)
        params.pop(self.lookup_gte_kwarg, None)
        return [{
            'get_query': params,
            'empty_filter': cl.get_query_string(remove=self.expected_parameters()),
            'selected': self.selected(cl)
        }]

    def selected(self, cl):
        return len(set(cl.params.keys()).intersection(self.expected_parameters())) > 0

    def expected_parameters(self):
        return [
            '%s%s__gte' % (self.lookup_field, self.suffix),
            '%s%s__lte' % (self.lookup_field, self.suffix)
        ]

    def queryset(self, request, queryset):
        if self.form.is_valid():
            params = dict()
            for key, value in self.form.cleaned_data.items():
                if value:
                    params.setdefault(key, value)
            return queryset.filter(**params)
        return queryset


class RelatedDropDownFilter(RelatedFieldListFilter):
    template = 'admin/dropdown_filter.html'

    @classmethod
    def bind_title(cls, title):
        class TitledRelatedDropdownFilter(RelatedDropDownFilter):

            def __init__(self, *args, **kwargs):
                super(TitledRelatedDropdownFilter, self).__init__(*args, **kwargs)
                self.title = title
        return TitledRelatedDropdownFilter


class ObjectRelatedDropdownFilter(RelatedDropDownFilter):
    def has_relation(self, obj, field):
        related_objects = getattr(obj, field.related_query_name(), None)
        return related_objects and related_objects.exists()

    def field_choices(self, field, request, model_admin):
        related_model = get_model_from_relation(self.field)
        choices = []
        for choice, title in field.get_choices(include_blank=False):
            choice_object = related_model.objects.get(id=choice)
            if self.has_relation(choice_object, field):
                choices.append((choice, title))
        return choices

    @classmethod
    def bind_title(cls, title):
        class TitledRelatedDropdownFilter(ObjectRelatedDropdownFilter):
            def __init__(self, *args, **kwargs):
                super(TitledRelatedDropdownFilter, self).__init__(*args, **kwargs)
                self.title = title

        return TitledRelatedDropdownFilter


class FieldDropDownFilter(AllValuesFieldListFilter):
    template = 'admin/dropdown_filter.html'

    def choices(self, cl):
        """
        Use choice display strings
        """
        choices = list(super(FieldDropDownFilter, self).choices(cl))
        if self.field.choices:
            new_choices = []
            for item in choices:
                key = str(item['display'])
                if not key:
                    new_choices.insert(0, item)
                    continue
                if key in self.field.choices._display_map:
                    display = self.field.choices._display_map[key]
                else:
                    display = item['display']
                new_choices.append({
                    'display': display,
                    'query_string': item['query_string'],
                    'selected': item['selected']
                })
            choices = new_choices
        return choices

    @classmethod
    def bind_title(cls, title):
        class TitledFieldDropdownFilter(FieldDropDownFilter):
            def __init__(self, *args, **kwargs):
                super(TitledFieldDropdownFilter, self).__init__(*args, **kwargs)
                self.title = title

        return TitledFieldDropdownFilter

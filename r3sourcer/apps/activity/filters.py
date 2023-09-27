from datetime import timedelta

from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _
from django.contrib import admin

from r3sourcer.apps.activity.models import Activity
from r3sourcer.apps.core.service import factory
from r3sourcer.apps.core.models import Contact
from r3sourcer.helpers.datetimes import utc_now


class ActivityTypeFilter(admin.SimpleListFilter):
    """ Filter by entity_object_name """

    parameter_name = 'activity_type'
    title = _("Activity type")
    template = 'admin/dropdown_filter.html'

    def lookups(self, request, model_admin):
        results = []
        queryset = Activity.objects.values_list('entity_object_name', flat=True).distinct()
        for name in queryset:
            try:
                model = factory.get_instance_class(name, fail_fast=True)
                results.append((name, model._meta.verbose_name))
            except Exception as e:
                pass
        return results

    def queryset(self, request, queryset):
        if self.value():
            return Activity.objects.filter(entity_object_name=self.value())
        return queryset


class OnlyMyActivityFilter(admin.SimpleListFilter):
    """ Return only current users' activities """

    title = _("Contact")
    parameter_name = "only_contact_id"
    template = 'admin/dropdown_filter.html'

    def lookups(self, request, model_admin):
        choices = [(c.id, str(c)) for c in Contact.objects.all().iterator()]
        choices.insert(0, ('0', _("My")))
        return choices

    def queryset(self, request, queryset):
        if self.value() == '0':
            id_list = request.user.contact.values_list('id', flat=True)
            return queryset.filter(contact_id__in=id_list)
        if self.value():
            return queryset.filter(contact_id=self.value())
        return queryset.all()


class ActivityExtraFilter(admin.filters.SimpleListFilter):

    _field1 = '{}__gte'
    _field2 = '{}__lte'

    _field3 = '{}__lte'
    _field4 = '{}__gte'
    title = None

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)

        for param in self.expected_parameters():
            if param in params:
                self.used_parameters[param] = params.pop(param)

    def has_output(self):
        return True

    def choices(self, cl):
        """
        Pop the original parameters, and return the date filter & other filter
        parameters.
        """
        choices = [
            {
                'display': _("All"),
                'selected': cl.get_query_string({}, self.expected_parameters()) == cl.get_query_string({}, []),
                'query_string': cl.get_query_string({}, self.expected_parameters())
            }
        ]
        selected = False
        for display, query in self.get_links(cl):
            _selected = cl.get_query_string(query, []) == cl.get_query_string()
            if not selected and _selected:
                selected = _selected
            choices.append({
                'display': display,
                'selected': _selected,
                'query_string': cl.get_query_string(query, [])
            })
        if not selected:
            choices[0]['selected'] = True
        return choices

    def get_links(self, cl):
        result = list()
        now_date_time = utc_now().date()
        yesterday = (now_date_time - timedelta(days=1))  # .replace(hour=0, minute=0, second=0)
        tomorrow = (now_date_time + timedelta(days=1))  # .replace(hour=23, minute=59, second=59)
        tomorrow_start = tomorrow  # .replace(hour=0, minute=0, second=0)
        tomorrow_end = tomorrow  # .replace(hour=23, minute=59, second=59)
        monday = (
        now_date_time - timedelta(days=now_date_time.weekday()))  # .replace(hour=0, minute=0, second=0)
        sunday = (now_date_time + timedelta(days=(7 - now_date_time.weekday())))  # .replace(hour=23, minute=59, second=59)
        next_monday = monday + timedelta(days=7)
        next_sunday = sunday + timedelta(days=7)

        # actual
        data_dict = {
            self._field1: '',
            self._field2: date_format(tomorrow),
            self._field3: '',
            self._field4: date_format(yesterday),
            'done__exact': 0
        }
        result.append((_("Actual"), data_dict))

        # overdue
        data_dict = {
            self._field1: '',
            self._field3: '',
            self._field2: date_format(now_date_time),
            self._field4: '',
            'done__exact': 0
        }
        result.append((_("Overdue"), data_dict))

        # today
        data_dict = {
            self._field1: date_format(now_date_time),
            self._field2: date_format(now_date_time),
            self._field3: '',
            self._field4: ''
        }
        result.append((_("Today"), data_dict))

        # tomorrow
        data_dict = {
            self._field1: date_format(tomorrow_start),
            self._field2: date_format(tomorrow_end),
            self._field3: '',
            self._field4: '',
        }
        result.append((_("Tomorrow"), data_dict))

        # this week
        data_dict = {
            self._field1: '',
            self._field2: date_format(sunday),
            self._field3: '',
            self._field4: date_format(monday),
        }
        result.append((_("This week"), data_dict))

        # next week
        data_dict = {
            self._field1: '',
            self._field2: date_format(next_sunday),
            self._field4: date_format(next_monday),
            self._field3: ''
        }
        result.append((_("Next week"), data_dict))

        # future
        data_dict = {
            self._field1: '',
            self._field2: '',
            self._field3: '',
            self._field4: date_format(next_sunday),
        }
        result.append((_("Future"), data_dict))

        # past
        data_dict = {
            self._field1: '',
            self._field2: date_format(yesterday),
            self._field3: '',
            self._field4: ''
        }

        result.append((_("Past"), data_dict))
        return result

    def expected_parameters(self):
        return [
            self._field1,
            self._field2,
            self._field3,
            self._field4,
            'done__exact'
        ]

    def queryset(self, request, queryset):
        return queryset


def make_actuality_filter(field1, field2, title):

    class ExtendActivityFilter(ActivityExtraFilter):

        def __init__(self, *args, **kwargs):
            self._field1 = self._field1.format(field1)
            self._field2 = self._field2.format(field2)

            self._field3 = self._field3.format(field1)
            self._field4 = self._field4.format(field2)

            self.title = title

            super(ExtendActivityFilter, self).__init__(*args, **kwargs)

    return ExtendActivityFilter

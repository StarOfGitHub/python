from django import template
from django.contrib.admin.templatetags.admin_list import (result_headers,
                                                          result_hidden_fields,
                                                          results)

register = template.Library()


@register.filter()
def by_index(iterable_list, index):
    """
    Return object by index from iterable list
    """
    return iterable_list[index]


@register.inclusion_tag("admin/activity/change_list_results.html")
def activity_result_list(cl, extra_conditions):
    """
    Extend django `result_list` tag with custom template variable `extra_conditions`
    """
    headers = list(result_headers(cl))
    num_sorted_fields = 0
    for h in headers:
        if h['sortable'] and h['sorted']:
            num_sorted_fields += 1
    return {'cl': cl,
            'result_hidden_fields': list(result_hidden_fields(cl)),
            'result_headers': headers,
            'num_sorted_fields': num_sorted_fields,
            'results': list(results(cl)),
            'extra_conditions': extra_conditions}


@register.filter()
def extra_classes(obj, conditions):
    """
    Return joined css classes by condition.

    :param obj: Model instance
    :param conditions: iterable object of tuples: [(field_name, value, css_class)]
    :return str: joined css classes
    """
    class_results = set()
    for cond in conditions:
        field, comp_value, cls = cond
        value = getattr(obj, field, None)
        if callable(value):
            value = value()
        if comp_value == value:
            class_results.add(cls)
    return ' '.join(class_results)

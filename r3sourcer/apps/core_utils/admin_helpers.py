from django.urls import reverse
from django.utils.safestring import mark_safe


def get_instance_admin_url(instance, text=None, as_url=False):
    """
    Return instance object admin url

    :param instance: models.Model subclass
    :param text: str Verbose name in a tag
    :param as_url: bool Return url or "a" tag
    :return:
    """

    try:
        link = reverse('admin:{app}_{model}_change'.format(
                app=instance._meta.app_label,
                model=instance._meta.model_name),
                args=[instance.id]
        )
    except Exception:
        link = 'javascript:void(0);'
    if as_url:
        return link
    return mark_safe('<a href="{}">{}</a>'.format(link, text or instance))

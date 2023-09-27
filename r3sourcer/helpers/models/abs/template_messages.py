import collections
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _

from .uuid_models import UUIDModel


class TemplateMessage(UUIDModel):

    INVALID_DEEP_MESSAGE = _("Max level deep: %s")

    INTERPOLATE_START = '[['
    INTERPOLATE_END = ']]'
    DELIMITER = '__'
    MAX_LEVEL_DEEP = 5

    TYPE_CHOICES = ()

    name = models.CharField(
        max_length=256,
        default="",
        verbose_name=_("Name"),
        db_index=True
    )

    slug = models.SlugField()

    type = models.CharField(
        max_length=8,
        choices=TYPE_CHOICES,
        verbose_name=_("Type")
    )

    subject_template = models.CharField(
        max_length=256,
        default="",
        verbose_name=_("Subject template"),
        blank=True
    )

    message_text_template = models.TextField(
        default="",
        verbose_name=_("Text template"),
        blank=True
    )

    message_html_template = models.TextField(
        default="",
        verbose_name=_("HTML template"),
        blank=True
    )

    reply_timeout = models.IntegerField(
        default=10,
        verbose_name=_("Reply timeout"),
        help_text=_("Minutes")
    )

    delivery_timeout = models.IntegerField(
        default=10,
        verbose_name=_("Delivery timeout"),
        help_text=_("Minutes")
    )

    company = models.ForeignKey(
        'core.Company',
        verbose_name=_("Master company"),
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True
        unique_together = ('name', 'company', 'type')

    def __str__(self):
        return self.name

    @classmethod
    def is_owned(cls):
        return False

    def clean(self):
        """
        Clean all template layers
        """
        for field in ['message_html_template',
                      'message_text_template',
                      'subject_template']:
            if getattr(self, field):
                arguments = self.get_require_params(getattr(self, field))
                for a in arguments:
                    if len(a.split(self.DELIMITER)) - 1 > self.MAX_LEVEL_DEEP:
                        raise ValidationError(
                            {field: self.INVALID_DEEP_MESSAGE % self.MAX_LEVEL_DEEP}
                        )

    def compile(self, **params):
        """
        Template compilation, variables substitution.
        Use params dict to pass variables into the template.
        Example:
            params = {
                'user': {'first_name': 'John',
                        'last_name': 'Davidson',
                        'contact': contact_instance},
                'starts_at': datetime.now(),
                'contact': Contact.objects.last()
            }
        """
        subject_compiled, text_compiled, html_compiled = self.compile_string(
            self.subject_template,
            self.message_text_template,
            self.message_html_template,
            **params)

        return {
            'id': self.id,
            'text': text_compiled,
            'html': html_compiled,
            'subject': subject_compiled
        }

    @classmethod
    def get_dict_values(cls, params, *rows, use_lookup=True):
        """Return dict with parsed variables as keys and params as its values.

        :param params: dict of variables
        :param rows: list of templates
        :param use_lookup: using lookup notation

        :return: dict
        """

        values_dict = dict()

        for parsed_item in cls.get_require_params(*rows, use_lookup=use_lookup):

            if parsed_item in params:
                values_dict.setdefault(parsed_item, params.get(parsed_item))

            split_parameter = parsed_item.split(cls.DELIMITER)[:cls.MAX_LEVEL_DEEP]

            parameter = ""
            special_parameter = split_parameter[0]

            for p in list(split_parameter):

                if special_parameter in params:
                    split_parameter = [special_parameter] + split_parameter[1:]
                    break
                split_parameter = split_parameter[1:]
                if parameter:
                    parameter = '{}{}{}'.format(parameter, cls.DELIMITER, p)
                else:
                    parameter = '{}'.format(parameter)
                if len(split_parameter) == 0:
                    break
                special_parameter = '{}{}{}'.format(
                    special_parameter,
                    cls.DELIMITER,
                    split_parameter[0]
                )

            if len(split_parameter) == 0:
                continue

            value = params[split_parameter[0]]

            for index, t in enumerate(split_parameter):
                parameter = '{}{}'.format(parameter, t)
                values_dict.setdefault(parameter, value)
                if len(split_parameter) - 1 == index:
                    continue

                key = split_parameter[index + 1]

                # handler
                if isinstance(value, collections.Iterable) and not hasattr(value, key):
                    try:
                        value = value[key]
                    except Exception:
                        break
                else:
                    if key not in ['delete', 'save', 'update', 'fetch_remote']:
                        if hasattr(value, key):
                            value = getattr(value, key)
                        else:
                            break

                # checking for callable
                if callable(value):
                    value = value()

                parameter = '{}{}'.format(parameter, cls.DELIMITER)
        return values_dict

    @classmethod
    def get_require_params(cls, *rows, use_lookup=True):
        """Get all variable names from multiple templates.
        Use use_lookup=False to disable lookups (lookup will parse
         variable like user__first_name).

        :param rows: templates list
        :param use_lookup: bool - using lookup notation, default True

        :return: set of names variables'
        """
        pattern = '{start}\\s*{pattern}\\s*{end}'.format(
            start=re.escape(cls.INTERPOLATE_START),
            pattern='(?P<param>[a-z]{1}[a-z\_0-9]*)',
            end=re.escape(cls.INTERPOLATE_END)
        )

        # get all param names
        parsed_params = set()
        for r in rows:
            parsed_params |= set(re.findall(pattern, r, re.I))

        if not use_lookup:
            parsed_params = map(lambda x: x.split(cls.DELIMITER)[0], parsed_params)

        return set(parsed_params)

    @classmethod
    def compile_string(cls, *raw_strings, **params):
        """Replace variables on param values.

        :param raw_strings: templates list
        :param params: variables dict
        :return: compiled rows
        """

        raw_strings = list(raw_strings)

        values_dict = cls.get_dict_values(params, *raw_strings)
        for param, value in values_dict.items():
            pattern = "{start}\\s*{param}\\s*{end}".format(
                start=re.escape(cls.INTERPOLATE_START),
                end=re.escape(cls.INTERPOLATE_END),
                param=param
            )

            value = str(value)
            for index, r in enumerate(raw_strings):
                raw_strings[index] = re.sub(pattern, value, r)

        return raw_strings

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.slug = slugify(self.name)

        super().save(*args, **kwargs)

from django.utils.translation import ugettext_lazy as _


CONTAINER_ROW = 'row'
CONTAINER_TABLE = 'table'
CONTAINER_COLLAPSE = 'collapse'
CONTAINER_HIDDEN = 'hidden'
CONTAINER_COLUMN = 'column'
CONTAINER_TABS = 'tabs'
CONTAINER_GROUP = 'group'

CONTAINER_TYPES = (
    CONTAINER_ROW, CONTAINER_TABLE, CONTAINER_COLLAPSE, CONTAINER_HIDDEN, CONTAINER_COLUMN, CONTAINER_TABS,
    CONTAINER_GROUP
)

FIELD_RADIO_GROUP = 'radio_group'
FIELD_CHECKBOX_GROUP = 'checkbox_group'
FIELD_BUTTON = 'button'
FIELD_LINK = 'link'
FIELD_SUBMIT = 'submit'
FIELD_PASSWORD = 'password'
FIELD_RELATED = 'related'
FIELD_STATIC = 'static'
FIELD_STATIC_ICON = 'static'
FIELD_SELECT = 'select'
FIELD_DATE = 'date'
FIELD_DATETIME = 'datetime'
FIELD_TIME = 'time'
FIELD_CHECKBOX = 'checkbox'
FIELD_RADIO = 'radio'
FIELD_TEXT = 'text'
FIELD_TEXTAREA = 'textarea'
FIELD_RULE = 'rule'
FIELD_PICTURE = 'picture'
FIELD_FILE = 'file'
FIELD_ICON = 'icon'
FIELD_TIMELINE = 'timeline'
FIELD_LIST = 'list'
FIELD_SCORE = 'score'
FIELD_SELECT_MULTIPLE = 'multiple'
FIELD_JOB_DATES = 'jobdates'
FIELD_SKILLS = 'skills'
FIELD_TAGS = 'tags'
FIELD_INFO = 'info'
FIELD_RANGE = 'range'
FIELD_ADDRESS = 'address'
FIELD_NUMBER = 'number'

DATEPICKER_TYPES = (FIELD_TIME, FIELD_DATE, FIELD_DATETIME)
NON_FIELDS_TYPES = (FIELD_BUTTON, FIELD_LINK, FIELD_SUBMIT, FIELD_TIMELINE, FIELD_LIST)

METADATA_LIST_TYPE = 'list'
METADATA_FORM_TYPE = 'form'
METADATA_FORMSET_TYPE = 'formset'
METADATA_FORMADD_TYPE = 'formadd'

DEFAULT_ACTION_POST = 'emptyPost'
DEFAULT_ACTION_EDIT = 'editForm'
DEFAULT_ACTION_DELETE = 'delete'
DEFAULT_ACTION_ADD = 'addForm'
DEFAULT_ACTION_LIST = 'openList'
DEFAULT_ACTION_SEND = 'send'
DEFAULT_ACTION_LINK = 'link'
DEFAULT_ACTION_SEND_SMS = 'sendSMS'
DEFAULT_ACTION_SEND_EMAIL = 'sendEmail'
DEFAULT_ACTION_MODAL_EDIT = 'editModal'


BUTTON_DELETE = {
    'type': FIELD_BUTTON,
    'icon': 'fa-times-circle',
    'field': 'id',
    'action': DEFAULT_ACTION_DELETE,
    'text_color': '#f32700',
    'title': _('Delete'),
}

BUTTON_EDIT = {
    'type': FIELD_BUTTON,
    'icon': 'fa-pencil',
    'field': 'id',
    'action': DEFAULT_ACTION_EDIT,
    'text_color': '#f0ad4e',
    'title': _('Edit'),
}

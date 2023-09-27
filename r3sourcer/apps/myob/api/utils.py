import copy

from . settings import MYOB_APP


def get_myob_app_info():
    app_data = copy.copy(MYOB_APP)
    return app_data

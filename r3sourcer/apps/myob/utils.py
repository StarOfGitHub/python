from django.apps import apps


def get_app_model(app, model_name):
    try:
        return apps.get_app_config(app).get_model(model_name)
    except LookupError:
        return None

import inspect


def workflow_function(func):
    func._workflow = True
    return func


def get_model_workflow_functions(model):
    functions_names = []
    for key, value in inspect.getmembers(model, predicate=inspect.isfunction):
        if hasattr(value, "_workflow"):
            functions_names.append(key)
    return functions_names

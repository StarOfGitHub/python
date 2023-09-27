from functools import wraps


def save_decorator(method, endless_logger):
    """
    Decorator for save method of the model. After saving of the
    model calls functions for logging object changes.
    """
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        just_added = self._state.adding
        old_instance = None
        result = method(self, *args, **kwargs)
        if self.id:
            if not just_added:
                old_instance = self.__class__.objects.get(id=self.id)

            if just_added:
                endless_logger.log_instance_change(self, transaction_type='create')
            else:
                endless_logger.log_instance_change(self, old_instance=old_instance, transaction_type='update')

        return result
    return wrapper


def delete_decorator(method, endless_logger):
    """
    Decorator for delete method of the model. After saving of the
    model calls functions for logging object changes.
    """
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        old_instance = self.__class__.objects.get(id=self.id)
        result = method(self, *args, **kwargs)
        endless_logger.log_instance_change(self, old_instance=old_instance, transaction_type='delete')
        return result
    return wrapper

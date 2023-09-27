from typing import Callable, Iterable


def propagate_row_to_list(storage: list, key, data) -> None:
    storage.append(data)


def qs_to_dict(propagate_row_fn: Callable, qs: Iterable) -> None:
    list(map(propagate_row_fn, qs))

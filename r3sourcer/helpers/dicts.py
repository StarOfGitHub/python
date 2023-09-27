from collections import Callable
from functools import partial
from typing import Union

# Type annotations section
dict_default_return_types = Union[list]


def __list() -> list:
    return list()


def dict_default(default_value: Callable,
                 container: dict,
                 key: str) -> dict_default_return_types:
    return container.setdefault(key, default_value())


dict_default_list = partial(dict_default, __list)

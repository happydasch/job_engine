"""Shared utility functions for the Job Engine core.

Provides:
- ``create_yaml()`` — factory for a ruamel.yaml round-trip YAML instance
- ``singleton`` — decorator for the lazy-init singleton pattern
"""

import functools
import logging
from typing import Any

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YAML factory
# ---------------------------------------------------------------------------


def create_yaml() -> YAML:
    """Return a round-trip ruamel.yaml YAML instance with standard settings.

    Preserves quotes, comments, and key ordering on write — the standard
    configuration needed by every config module that reads/writes YAML files.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


# ---------------------------------------------------------------------------
# Singleton decorator
# ---------------------------------------------------------------------------


def singleton(cls):
    """Decorator that adds a lazy-init ``get_instance()`` classmethod.

    Usage::

        @singleton
        class MyService:
            def __init__(self, ...):
                ...

        # Instead of _instance = None / get_my_service() boilerplate:
        instance = MyService.get_instance(...)

    The first call to ``get_instance(*args, **kwargs)`` creates the instance;
    subsequent calls return the cached instance, ignoring arguments.
    """
    _instance = None

    @functools.wraps(cls)
    def get_instance(*args: Any, **kwargs: Any) -> Any:
        nonlocal _instance
        if _instance is None:
            _instance = cls(*args, **kwargs)
        return _instance

    cls.get_instance = staticmethod(get_instance)  # type: ignore[attr-defined]
    return cls

"""Extensible plugin interface for the Job Engine.

Plugins can hook into key events:
- on_analysis_start / on_analysis_complete (LLM analysis)
- on_application_create / on_application_status_change (application lifecycle)

Usage:
    from job_engine.plugin import PluginBase, plugin_registry

    class MyPlugin(PluginBase):
        name = "my_plugin"

        def on_analysis_complete(self, job_id, result):
            # Do something with the result
            pass

    plugin_registry.register(MyPlugin())
"""

import importlib.util
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from job_engine.config import config as _config

logger = logging.getLogger(__name__)


class PluginBase(ABC):
    """Abstract base class for all plugins.

    Subclass this and override the hooks you need.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier."""
        ...

    @property
    def version(self) -> str:
        """Plugin version string."""
        return "1.0.0"

    @property
    def description(self) -> str:
        """Human-readable description."""
        return ""

    # ── Hooks ────────────────────────────────────────────────────────────────

    def on_analysis_start(self, job_id: int, profile: dict[str, Any]) -> None:
        """Called before LLM analysis of a job begins.

        Args:
            job_id: The job ID being analyzed.
            profile: The user profile dict.
        """
        pass

    def on_analysis_complete(self, job_id: int, result: dict[str, Any] | None) -> None:
        """Called after LLM analysis completes.

        Args:
            job_id: The job ID that was analyzed.
            result: The analysis result dict, or None if analysis failed.
        """
        pass

    def on_application_create(self, application: dict[str, Any]) -> None:
        """Called when a new application is created.

        Args:
            application: The application data dict.
        """
        pass

    def on_application_status_change(
        self, application: dict[str, Any], old_status: str, new_status: str
    ) -> None:
        """Called when an application's status changes.

        Args:
            application: The application data dict.
            old_status: The previous status.
            new_status: The new status.
        """
        pass


class PluginRegistry:
    """Singleton registry for plugins.

    Registered plugins receive event notifications through their hook methods.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}
        self._loaded = False

    def register(self, plugin: PluginBase) -> None:
        """Register a plugin instance.

        Args:
            plugin: The plugin instance to register.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' is already registered")
        self._plugins[plugin.name] = plugin
        logger.info("Registered plugin: %s v%s", plugin.name, plugin.version)

    def unregister(self, name: str) -> None:
        """Unregister a plugin by name.

        Args:
            name: The plugin name to unregister.
        """
        if name in self._plugins:
            del self._plugins[name]
            logger.info("Unregistered plugin: %s", name)

    def get_hooks(self, event: str) -> list[Callable[..., None]]:
        """Get all registered hook functions for an event.

        Args:
            event: The event name (e.g. 'on_analysis_complete').

        Returns:
            List of callable hook functions.
        """
        return [
            getattr(plugin, event)
            for plugin in self._plugins.values()
            if hasattr(plugin, event) and callable(getattr(plugin, event))
        ]

    def trigger(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Trigger an event on all registered plugins.

        Args:
            event: The event name (e.g. 'on_analysis_complete').
            *args: Positional arguments to pass to the hook.
            **kwargs: Keyword arguments to pass to the hook.
        """
        for hook in self.get_hooks(event):
            try:
                hook(*args, **kwargs)
            except Exception as e:
                logger.error("Plugin hook %s failed: %s", event, e, exc_info=True)

    def discover(self, search_paths: list[str | Path] | None = None) -> int:
        """Discover and load plugins from filesystem paths.

        Looks for Python files in the given search paths, imports them,
        and registers any PluginBase subclasses found.

        Args:
            search_paths: List of directory paths to search. Defaults to
                          ['data/plugins'].

        Returns:
            Number of plugins discovered and loaded.
        """
        if search_paths is None:
            search_paths = [_config.data_dir / "plugins"]

        count = 0
        for search_path in search_paths:
            path = Path(search_path)
            if not path.exists():
                continue

            for py_file in sorted(path.glob("*.py")):
                try:
                    spec = importlib.util.spec_from_file_location(f"plugin_{py_file.stem}", py_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # Find PluginBase subclasses in the module
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (
                                isinstance(attr, type)
                                and issubclass(attr, PluginBase)
                                and attr is not PluginBase
                            ):
                                plugin = attr()
                                self.register(plugin)
                                count += 1
                except Exception as e:
                    logger.warning("Failed to load plugin from %s: %s", py_file, e)

        self._loaded = True
        return count

    @property
    def plugins(self) -> dict[str, PluginBase]:
        """Get all registered plugins."""
        return dict(self._plugins)

    @property
    def loaded(self) -> bool:
        """Whether plugins have been discovered."""
        return self._loaded


# Global singleton
plugin_registry = PluginRegistry()

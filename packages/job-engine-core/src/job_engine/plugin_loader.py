"""Plugin loading and management on top of :mod:`job_engine.plugin`.

The dashboard and core share one plugin registry (``plugin_registry``).
``PluginLoader`` reconciles the Python plugins discovered on disk
(``data/plugins/*.py``) with the enabled/disabled registry stored in
``data/plugins.yml``:
- ``init_plugins()`` discovers plugin modules and keeps only the enabled ones.
- ``set_enabled()`` toggles a plugin on/off and persists the flag.
- ``list_plugins()`` returns a dashboard-friendly description of each plugin.

The plugin base class (`PluginBase`) and the registry (`PluginRegistry`) live in
``job_engine.plugin``; the loader is intentionally a thin management layer so
that pipeline code only depends on the singleton registry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from job_engine.config import config as _config
from job_engine.plugin import PluginRegistry, plugin_registry

logger = logging.getLogger(__name__)

_PLUGINS_KEY = "plugins"


class PluginLoader:
    """Discovers, registers, and tracks the enable state of engine plugins.

    Args:
        registry: The plugin registry to operate on. Defaults to the shared
            ``plugin_registry`` singleton.
        config_path: Path to the ``plugins.yml`` registry file. Defaults to
            ``<data_dir>/plugins.yml``.
        plugins_dir: Directory to scan for ``.py`` plugin modules. Defaults to
            ``<data_dir>/plugins``.
    """

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        config_path: Path | None = None,
        plugins_dir: Path | None = None,
    ) -> None:
        self._registry = registry or plugin_registry
        self._config_path = config_path or _config.data_dir / "plugins.yml"
        self._plugins_dir = plugins_dir or _config.data_dir / "plugins"

    # ── Registry persistence ─────────────────────────────────────────────────

    def load_config(self) -> dict[str, Any]:
        """Return the plugin registry dict from plugins.yml (empty if absent)."""
        if not self._config_path.exists():
            return {}
        import ruamel.yaml

        yaml = ruamel.yaml.YAML(typ="safe")
        with self._config_path.open("r", encoding="utf-8") as fh:
            data = yaml.load(fh) or {}
        return dict(data.get(_PLUGINS_KEY) or {})

    def save_config(self, plugins: dict[str, Any]) -> None:
        """Write the plugin registry dict to plugins.yml."""
        import ruamel.yaml

        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        yaml = ruamel.yaml.YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        with self._config_path.open("w", encoding="utf-8") as fh:
            yaml.dump({_PLUGINS_KEY: plugins}, fh)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def init_plugins(self) -> int:
        """Discover plugin modules and disable any marked disabled in the YAML.

        Returns the number of plugins left enabled after reconciliation.
        """
        discovered = self._registry.discover([self._plugins_dir])
        cfg = self.load_config()
        for name in list(self._registry.plugins):
            entry = cfg.get(name, {})
            if isinstance(entry, dict) and entry.get("enabled", True) is False:
                self._registry.unregister(name)
                logger.info("Plugin '%s' is disabled in %s", name, self._config_path)
        if discovered:
            logger.info("Discovered %d plugin module(s)", discovered)
        return len(self._registry.plugins)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a plugin by name.

        Persists the enable flag and (re)registers/unregisters the plugin if its
        module is loadable. Returns True if a plugin with that name is present
        after the operation.
        """
        cfg = self.load_config()
        entry = cfg.get(name, {})
        if not isinstance(entry, dict):
            entry = {}
        entry["enabled"] = enabled
        cfg[name] = entry
        self.save_config(cfg)

        if enabled:
            # Re-discover so the module (re)registers itself, then reconcile.
            self._registry.discover([self._plugins_dir])
        else:
            self._registry.unregister(name)

        present = name in self._registry.plugins
        logger.info("Plugin '%s' %s", name, "enabled" if enabled else "disabled")
        return present

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return a list of plugin descriptors for the dashboard."""
        cfg = self.load_config()
        result: list[dict[str, Any]] = []
        for name, plugin in self._registry.plugins.items():
            entry = cfg.get(name, {}) if isinstance(cfg.get(name), dict) else {}
            result.append(
                {
                    "name": name,
                    "version": getattr(plugin, "version", "1.0.0"),
                    "description": getattr(plugin, "description", ""),
                    "enabled": entry.get("enabled", True) is not False,
                }
            )
        result.sort(key=lambda p: p["name"])
        return result


# Shared singleton for dashboard routes
_loader_instance: PluginLoader | None = None


def get_plugin_loader() -> PluginLoader:
    """Lazy-init singleton for PluginLoader."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = PluginLoader()
    return _loader_instance

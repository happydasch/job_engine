"""Tests for the plugin loader / registry management layer."""

from pathlib import Path

from job_engine.plugin import PluginRegistry
from job_engine.plugin_loader import PluginLoader

SAMPLE_PLUGIN = """\
from job_engine.plugin import PluginBase

class SamplePlugin(PluginBase):
    name = "sample_plugin"
    version = "0.1.0"
    description = "A test plugin"

    def __init__(self):
        self.calls = []

    def on_analysis_complete(self, job_id, result):
        self.calls.append((job_id, result))
"""


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "sample_plugin.py").write_text(SAMPLE_PLUGIN, encoding="utf-8")
    config_path = tmp_path / "plugins.yml"
    config_path.write_text("plugins: {}\n", encoding="utf-8")
    return plugins_dir, config_path


def test_discover_loads_plugin(tmp_path):
    plugins_dir, config_path = _seed(tmp_path)
    loader = PluginLoader(
        registry=PluginRegistry(), config_path=config_path, plugins_dir=plugins_dir
    )
    assert loader.init_plugins() == 1
    assert "sample_plugin" in loader._registry.plugins
    assert loader.list_plugins()[0]["name"] == "sample_plugin"


def test_disable_and_re_enable(tmp_path):
    plugins_dir, config_path = _seed(tmp_path)
    loader = PluginLoader(
        registry=PluginRegistry(), config_path=config_path, plugins_dir=plugins_dir
    )
    loader.init_plugins()
    assert "sample_plugin" in loader._registry.plugins

    loader.set_enabled("sample_plugin", False)
    assert "sample_plugin" not in loader._registry.plugins

    loader.set_enabled("sample_plugin", True)
    assert "sample_plugin" in loader._registry.plugins
    # Enable state is persisted
    assert loader.load_config()["sample_plugin"]["enabled"] is True


def test_trigger_calls_hook(tmp_path):
    plugins_dir, config_path = _seed(tmp_path)
    registry = PluginRegistry()
    loader = PluginLoader(registry=registry, config_path=config_path, plugins_dir=plugins_dir)
    loader.init_plugins()
    plugin = registry.plugins["sample_plugin"]
    registry.trigger("on_analysis_complete", 7, {"ok": True})
    assert plugin.calls == [(7, {"ok": True})]

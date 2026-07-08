import importlib
import inspect
import logging
import os
import pkgutil
from typing import Any

from strategies.base import BaseStrategy
from runtime.models import StrategyPlugin, StrategyState, TriggerType

logger = logging.getLogger(__name__)

STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "..", "strategies")
INDICATORS_DIR = os.path.join(os.path.dirname(__file__), "..", "indicators")
CONDITIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "conditions")
OPERATORS_DIR = os.path.join(os.path.dirname(__file__), "..", "operators")
FUNCTIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "functions")


class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[str, type[BaseStrategy]] = {}
        self._plugins: dict[str, StrategyPlugin] = {}
        self._instances: dict[str, BaseStrategy] = {}
        self._states: dict[str, StrategyState] = {}
        self._discovered = False

    def register(self, key: str, cls: type[BaseStrategy], plugin: StrategyPlugin | None = None) -> None:
        self._strategies[key] = cls
        if plugin:
            self._plugins[key] = plugin
        logger.info("Strategy registered: %s (%s)", key, cls.__name__)

    def unregister(self, key: str) -> None:
        self._strategies.pop(key, None)
        self._plugins.pop(key, None)
        self._instances.pop(key, None)
        self._states.pop(key, None)

    def get_class(self, key: str) -> type[BaseStrategy] | None:
        return self._strategies.get(key)

    def get_instance(self, key: str) -> BaseStrategy | None:
        return self._instances.get(key)

    def set_instance(self, key: str, instance: BaseStrategy) -> None:
        self._instances[key] = instance

    def get_state(self, key: str) -> StrategyState:
        return self._states.get(key, StrategyState.DRAFT)

    def set_state(self, key: str, state: StrategyState) -> None:
        self._states[key] = state

    def enable(self, key: str) -> None:
        if key in self._plugins:
            self._plugins[key].enabled = True
        if key in self._states and self._states[key] in (StrategyState.READY, StrategyState.DRAFT):
            self._states[key] = StrategyState.READY

    def disable(self, key: str) -> None:
        if key in self._plugins:
            self._plugins[key].enabled = False
        if key in self._states and self._states[key] == StrategyState.RUNNING:
            self._states[key] = StrategyState.PAUSED

    def reload(self, key: str) -> bool:
        import time
        now = time.time()
        last = getattr(self, "_last_reload_time", 0)
        if now - last < 5:
            logger.warning("Reload throttled for %s — must wait 5s between reloads", key)
            return False
        self._last_reload_time = now
        try:
            cls = self._strategies.get(key)
            if not cls:
                return False
            module = inspect.getmodule(cls)
            if module:
                importlib.invalidate_caches()
                new_module = importlib.import_module(module.__name__)
                importlib.reload(new_module)
                members = inspect.getmembers(new_module, lambda m: inspect.isclass(m) and issubclass(m, BaseStrategy) and m is not BaseStrategy)
                for name, new_cls in members:
                    if name == cls.__name__:
                        self._strategies[key] = new_cls
                        self._instances.pop(key, None)
                        break
            logger.info("Strategy reloaded: %s", key)
            return True
        except Exception as e:
            logger.error("Failed to reload strategy %s: %s", key, e)
            return False

    def discover(self) -> list[str]:
        if self._discovered:
            return list(self._strategies.keys())
        self._discovered = True
        discovered = []
        for loader, module_name, is_pkg in pkgutil.iter_modules([STRATEGIES_DIR]):
            if module_name.startswith("_") or is_pkg:
                continue
            try:
                module = importlib.import_module(f"strategies.{module_name}")
                members = inspect.getmembers(
                    module,
                    lambda m: inspect.isclass(m) and issubclass(m, BaseStrategy) and m is not BaseStrategy,
                )
                for name, cls in members:
                    key = getattr(cls, "name", module_name)
                    description = getattr(cls, "description", "")
                    plugin = StrategyPlugin(
                        key=key,
                        name=name,
                        description=description,
                        path=f"strategies.{module_name}.{name}",
                    )
                    self.register(key, cls, plugin)
                    discovered.append(key)
                    logger.info("Discovered strategy: %s at %s", key, plugin.path)
            except Exception as e:
                logger.warning("Failed to load strategy module %s: %s", module_name, e)
        return discovered

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    def list_enabled(self) -> list[str]:
        return [k for k, p in self._plugins.items() if p.enabled]

    def list_running(self) -> list[str]:
        return [k for k, s in self._states.items() if s == StrategyState.RUNNING]

    def get_plugin(self, key: str) -> StrategyPlugin | None:
        return self._plugins.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._strategies


strategy_registry = StrategyRegistry()

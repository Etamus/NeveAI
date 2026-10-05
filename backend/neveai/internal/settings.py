"""Runtime settings with durable snapshots and optional cross-process updates."""

import json
from copy import deepcopy
from threading import RLock
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class SettingsStore:
    def __init__(self, document: dict, persist: Callable[[dict], None]):
        self.document = document
        self.persist = persist
        self.lock = RLock()

    def read(self, path: str):
        current = self.document
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
        return current

    def write(self, path: str, value):
        with self.lock:
            candidate = deepcopy(self.document)
            segments = path.split(".")
            parent = candidate
            for segment in segments[:-1]:
                parent = parent.setdefault(segment, {})
            parent[segments[-1]] = deepcopy(value)
            self.persist(candidate)
            self.document.clear()
            self.document.update(candidate)


class Setting(Generic[T]):
    __slots__ = (
        "env_name",
        "config_path",
        "env_value",
        "config_value",
        "value",
        "_store",
    )

    def __init__(
        self,
        name: str,
        path: str,
        fallback: T,
        store: SettingsStore,
        use_saved: bool = True,
    ):
        self.env_name = name
        self.config_path = path
        self.env_value = fallback
        self._store = store
        saved = store.read(path)
        self.config_value = saved
        self.value = saved if use_saved and saved is not None else fallback

    def __str__(self):
        return str(self.value)

    def update(self):
        saved = self._store.read(self.config_path)
        if saved is not None:
            self.value = saved

    def save(self):
        self._store.write(self.config_path, self.value)
        self.config_value = self.value


class RuntimeSettings:
    __slots__ = ("_entries", "_transport", "_namespace", "_sync_enabled", "_logger")

    def __init__(
        self, transport=None, namespace="neveai", sync_enabled=lambda: True, logger=None
    ):
        object.__setattr__(self, "_entries", {})
        object.__setattr__(self, "_transport", transport)
        object.__setattr__(self, "_namespace", namespace)
        object.__setattr__(self, "_sync_enabled", sync_enabled)
        object.__setattr__(self, "_logger", logger)

    def _cache_key(self, name):
        return f"{self._namespace}:config:{name}"

    def __getattr__(self, name):
        try:
            entry = self._entries[name]
        except KeyError:
            raise AttributeError(f"Config key '{name}' not found") from None
        if self._transport is not None and self._sync_enabled():
            payload = self._transport.get(self._cache_key(name))
            if payload is not None:
                try:
                    entry.value = json.loads(payload)
                except json.JSONDecodeError:
                    if self._logger is not None:
                        self._logger.error("Invalid JSON format in Redis for %s", name)
        return entry.value

    def __setattr__(self, name, value):
        if isinstance(value, Setting):
            self._entries[name] = value
            return
        if name not in self._entries:
            raise AttributeError(f"Config key '{name}' not found")
        entry = self._entries[name]
        previous = entry.value
        entry.value = value
        try:
            entry.save()
        except Exception:
            entry.value = previous
            raise
        if self._transport is not None and self._sync_enabled():
            self._transport.set(self._cache_key(name), json.dumps(value))

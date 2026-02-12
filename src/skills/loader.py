from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Callable, Iterator, Mapping, Sequence


SUPPORTED_HOOK_EVENTS = {
    "pre-dispatch",
    "post-accept",
    "pre-compact",
    "session-start",
}


class SkillLoaderError(ValueError):
    """Raised when skill manifests cannot be safely discovered or loaded."""


SkillHandler = Callable[[dict[str, Any], dict[str, Any]], Any]


@dataclass(frozen=True)
class SkillManifestHook:
    event: str
    handler: str
    timeout_seconds: float | None
    idempotent: bool


@dataclass(frozen=True)
class SkillManifest:
    schema_version: str
    name: str
    version: str
    description: str | None
    instructions: tuple[str, ...]
    scripts: dict[str, str]
    hooks: tuple[SkillManifestHook, ...]


@dataclass(frozen=True)
class LoadedSkill:
    manifest: SkillManifest
    path: Path
    manifest_path: Path


class SkillLoader:
    """Discovers skills and parses versioned manifests from configured directories."""

    def __init__(self, *, search_paths: Sequence[str | Path]) -> None:
        normalized_paths: list[Path] = []
        for index, candidate in enumerate(search_paths):
            path = Path(candidate).expanduser().resolve()
            if path in normalized_paths:
                continue
            if not path.exists():
                raise SkillLoaderError(f"search_paths[{index}] does not exist: {path}")
            normalized_paths.append(path)
        self._search_paths = tuple(normalized_paths)

    @property
    def search_paths(self) -> tuple[Path, ...]:
        return self._search_paths

    def discover(self) -> tuple[LoadedSkill, ...]:
        discovered: list[LoadedSkill] = []
        seen_names: dict[str, Path] = {}
        for manifest_path in self._iter_manifest_paths():
            loaded = self._load_manifest_file(manifest_path)
            conflict = seen_names.get(loaded.manifest.name)
            if conflict is not None:
                raise SkillLoaderError(
                    "duplicate skill name "
                    f"'{loaded.manifest.name}' in {conflict} and {loaded.path}"
                )
            seen_names[loaded.manifest.name] = loaded.path
            discovered.append(loaded)
        discovered.sort(key=lambda item: item.manifest.name)
        return tuple(discovered)

    def load_all(self) -> dict[str, LoadedSkill]:
        return {loaded.manifest.name: loaded for loaded in self.discover()}

    def load(self, name: str) -> LoadedSkill:
        normalized_name = _expect_non_empty_string(name, name="name")
        for loaded in self.discover():
            if loaded.manifest.name == normalized_name:
                return loaded
        raise SkillLoaderError(
            f"skill '{normalized_name}' was not found under {list(self._search_paths)}"
        )

    def resolve_handler(self, loaded_skill: LoadedSkill, handler_ref: str) -> SkillHandler:
        return resolve_skill_handler(loaded_skill, handler_ref)

    def _iter_manifest_paths(self) -> Iterator[Path]:
        manifest_paths: list[Path] = []
        for search_path in self._search_paths:
            direct_manifest = search_path / "skill.json"
            if direct_manifest.is_file():
                manifest_paths.append(direct_manifest)
                continue

            for child in sorted(search_path.iterdir()):
                if not child.is_dir():
                    continue
                child_manifest = child / "skill.json"
                if child_manifest.is_file():
                    manifest_paths.append(child_manifest)

        manifest_paths.sort()
        return iter(manifest_paths)

    def _load_manifest_file(self, manifest_path: Path) -> LoadedSkill:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SkillLoaderError(f"manifest is not valid JSON: {manifest_path}") from exc
        if not isinstance(payload, dict):
            raise SkillLoaderError(f"manifest root must be an object: {manifest_path}")

        manifest = parse_skill_manifest(payload)
        return LoadedSkill(
            manifest=manifest,
            path=manifest_path.parent,
            manifest_path=manifest_path,
        )


def parse_skill_manifest(payload: Mapping[str, Any]) -> SkillManifest:
    schema_version = _expect_non_empty_string(payload.get("schema_version"), name="schema_version")
    name = _expect_non_empty_string(payload.get("name"), name="name")
    version = _expect_non_empty_string(payload.get("version"), name="version")

    description_raw = payload.get("description")
    if description_raw is None:
        description = None
    else:
        description = _expect_non_empty_string(description_raw, name="description")

    instructions_raw = payload.get("instructions", [])
    if not isinstance(instructions_raw, list):
        raise SkillLoaderError("instructions must be a list when provided")
    instructions: list[str] = []
    for index, value in enumerate(instructions_raw):
        instructions.append(_expect_non_empty_string(value, name=f"instructions[{index}]"))

    scripts_raw = payload.get("scripts", {})
    if not isinstance(scripts_raw, Mapping):
        raise SkillLoaderError("scripts must be an object mapping names to paths")
    scripts: dict[str, str] = {}
    for key, value in scripts_raw.items():
        script_name = _expect_non_empty_string(key, name="scripts key")
        script_path = _expect_non_empty_string(value, name=f"scripts['{script_name}']")
        scripts[script_name] = script_path

    hooks_raw = payload.get("hooks", [])
    if not isinstance(hooks_raw, list):
        raise SkillLoaderError("hooks must be a list when provided")
    hooks: list[SkillManifestHook] = []
    for index, entry in enumerate(hooks_raw):
        if not isinstance(entry, Mapping):
            raise SkillLoaderError(f"hooks[{index}] must be an object")
        event = _normalize_hook_event(entry.get("event"), name=f"hooks[{index}].event")
        handler = _expect_non_empty_string(entry.get("handler"), name=f"hooks[{index}].handler")
        timeout_seconds = _normalize_optional_timeout(
            entry.get("timeout_seconds"),
            name=f"hooks[{index}].timeout_seconds",
        )
        idempotent = _normalize_optional_bool(
            entry.get("idempotent", True),
            name=f"hooks[{index}].idempotent",
        )
        hooks.append(
            SkillManifestHook(
                event=event,
                handler=handler,
                timeout_seconds=timeout_seconds,
                idempotent=idempotent,
            )
        )

    return SkillManifest(
        schema_version=schema_version,
        name=name,
        version=version,
        description=description,
        instructions=tuple(instructions),
        scripts=scripts,
        hooks=tuple(hooks),
    )


def resolve_skill_handler(loaded_skill: LoadedSkill, handler_ref: str) -> SkillHandler:
    normalized_ref = _expect_non_empty_string(handler_ref, name="handler_ref")
    module_ref, separator, attribute = normalized_ref.partition(":")
    if separator != ":" or not attribute:
        raise SkillLoaderError(
            f"handler '{normalized_ref}' must use '<module_or_file>:<callable>' format"
        )

    module = _load_handler_module(loaded_skill=loaded_skill, module_ref=module_ref)
    candidate = getattr(module, attribute, None)
    if candidate is None:
        raise SkillLoaderError(
            f"handler '{normalized_ref}' does not exist in module '{module_ref}'"
        )
    if not callable(candidate):
        raise SkillLoaderError(f"handler '{normalized_ref}' is not callable")
    return candidate


def _load_handler_module(*, loaded_skill: LoadedSkill, module_ref: str) -> ModuleType:
    if _is_file_module_ref(module_ref):
        module_path = (loaded_skill.path / module_ref).resolve()
        if not module_path.is_file():
            raise SkillLoaderError(
                f"handler module file does not exist for skill '{loaded_skill.manifest.name}': "
                f"{module_path}"
            )
        module_name = (
            f"daokit_skill_{loaded_skill.manifest.name.replace('-', '_')}_"
            f"{abs(hash(str(module_path)))}"
        )
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise SkillLoaderError(f"cannot import handler module from file: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    with _sys_path(str(loaded_skill.path), str(loaded_skill.path.parent)):
        try:
            return importlib.import_module(module_ref)
        except Exception as exc:
            raise SkillLoaderError(
                f"cannot import handler module '{module_ref}' for skill "
                f"'{loaded_skill.manifest.name}': {exc.__class__.__name__}: {exc}"
            ) from exc


@contextmanager
def _sys_path(*paths: str) -> Iterator[None]:
    original = list(sys.path)
    for path in reversed(paths):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    try:
        yield
    finally:
        sys.path[:] = original


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise SkillLoaderError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise SkillLoaderError(f"{name} must be a non-empty string")
    return normalized


def _normalize_optional_timeout(value: Any, *, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SkillLoaderError(f"{name} must be a positive number when provided")
    timeout = float(value)
    if timeout <= 0:
        raise SkillLoaderError(f"{name} must be > 0")
    return timeout


def _normalize_optional_bool(value: Any, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise SkillLoaderError(f"{name} must be a boolean")
    return value


def _normalize_hook_event(value: Any, *, name: str) -> str:
    normalized = _expect_non_empty_string(value, name=name).replace("_", "-").lower()
    if normalized not in SUPPORTED_HOOK_EVENTS:
        supported = ", ".join(sorted(SUPPORTED_HOOK_EVENTS))
        raise SkillLoaderError(f"{name} must be one of: {supported}")
    return normalized


def _is_file_module_ref(value: str) -> bool:
    return value.endswith(".py") or "/" in value or "\\" in value

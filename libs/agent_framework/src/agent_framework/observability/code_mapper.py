from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

logger = logging.getLogger("agent_framework.observability.code_mapper")


DEFAULT_OBSERVABILITY_MAPPING_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "observability_mapping.yaml"
)


@dataclass(frozen=True, slots=True)
class ObservabilityMappingEntry:
    """One entry of the external observability contract registry.

    ``label`` controls what downstream observability receives. ``action`` is an
    optional guardrail execution policy used only when a denied rail did not
    already declare a more specific action. ``aliases`` allow legacy/internal/
    external rail codes to resolve to the same semantic entry.

    A mapping may intentionally have no label and only define an action. In that
    case observability keeps the original semantic name while the framework can
    still use the entry to preserve legacy guardrail behaviour.
    """

    canonical_name: str
    label: str | None = None
    action: str | None = None
    aliases: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ObservabilityCodeMapper:
    """Observability contract registry shared by emission and guardrail policy.

    Backward-compatible YAML forms::

        mappings:
          guardrail.dlex_in: GRL.004

    Rich form::

        mappings:
          guardrail.revprec:
            label: GRL.005
            action: retry
            aliases: [REVPREC, TIM_REVPREC]

    Resolution is fail-open for observability and fail-safe for guardrail flow:
    an unknown name is emitted unchanged, while callers deciding a denied rail
    can fall back to BLOCK when :meth:`action_for` returns ``None``.
    """

    def __init__(self, mappings: Mapping[str, Any] | None = None, *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self._entries: dict[str, ObservabilityMappingEntry] = {}
        self._lookup: dict[str, str] = {}
        self._load_entries(dict(mappings or {}))

    @staticmethod
    def _norm(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _lookup_key(cls, value: Any) -> str:
        return cls._norm(value).casefold()

    def _load_entries(self, mappings: dict[str, Any]) -> None:
        for raw_name, raw_value in mappings.items():
            canonical = self._norm(raw_name)
            if not canonical:
                continue

            label: str | None = None
            action: str | None = None
            aliases: list[str] = []
            extra: dict[str, Any] = {}

            if isinstance(raw_value, str) or raw_value is None:
                # Historical compact syntax. ``None`` is allowed for an
                # action/alias-only entry written in expanded form later.
                label = self._norm(raw_value) or None
            elif isinstance(raw_value, dict):
                label = self._norm(
                    raw_value.get("label")
                    or raw_value.get("external")
                    or raw_value.get("external_code")
                    or raw_value.get("code")
                ) or None
                action = self._norm(raw_value.get("action") or raw_value.get("terminal_action")).lower() or None
                raw_aliases = raw_value.get("aliases", [])
                if isinstance(raw_aliases, str):
                    raw_aliases = [raw_aliases]
                if isinstance(raw_aliases, (list, tuple, set)):
                    aliases = [self._norm(item) for item in raw_aliases if self._norm(item)]
                extra = {
                    str(k): v for k, v in raw_value.items()
                    if k not in {"label", "external", "external_code", "code", "action", "terminal_action", "aliases"}
                }
            else:
                logger.warning(
                    "observability.mapping_entry_invalid name=%s type=%s; entry ignored",
                    canonical,
                    type(raw_value).__name__,
                )
                continue

            entry = ObservabilityMappingEntry(
                canonical_name=canonical,
                label=label,
                action=action,
                aliases=tuple(aliases),
                metadata=extra,
            )
            self._entries[canonical] = entry

            candidates = [canonical, *aliases]
            # Guardrail semantic keys automatically resolve their short code too,
            # so ``guardrail.revprec`` also matches ``REVPREC`` without requiring
            # an explicit alias. Explicit aliases remain useful for TIM_REVPREC,
            # ATH/HUMAN, renamed external rails, etc.
            if canonical.casefold().startswith("guardrail."):
                candidates.append(canonical.split(".", 1)[1])

            for candidate in candidates:
                key = self._lookup_key(candidate)
                if key:
                    self._lookup[key] = canonical

    @classmethod
    def from_yaml(cls, path: str | Path | None, *, enabled: bool = True) -> "ObservabilityCodeMapper":
        if not enabled or not path:
            return cls({}, enabled=enabled)
        requested_path = Path(path).expanduser()
        candidates: list[Path] = [requested_path]
        if not requested_path.is_absolute():
            candidates.append(Path.cwd() / requested_path)
            for root in sys.path:
                if root:
                    candidates.append(Path(root).expanduser() / requested_path)

        seen: set[str] = set()
        file_path: Path | None = None
        for candidate in candidates:
            try:
                key = str(candidate.resolve())
            except Exception:
                key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                file_path = candidate
                break

        if file_path is None:
            logger.warning(
                "observability.mapping_file_not_found path=%s cwd=%s candidates=%s; passthrough enabled",
                requested_path, Path.cwd(), list(seen),
            )
            return cls({}, enabled=enabled)
        try:
            raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.exception("observability.mapping_file_invalid path=%s; passthrough enabled", file_path)
            return cls({}, enabled=enabled)
        mappings = raw.get("mappings", raw) if isinstance(raw, dict) else {}
        if not isinstance(mappings, dict):
            logger.warning("observability.mapping_invalid_shape path=%s; passthrough enabled", file_path)
            mappings = {}
        instance = cls(mappings, enabled=enabled)
        logger.info(
            "observability.mapping_loaded enabled=%s path=%s mappings=%d",
            enabled, file_path.resolve(), len(instance.entries),
        )
        return instance

    def resolve(self, name: str | None, *, namespace: str | None = None) -> ObservabilityMappingEntry | None:
        """Resolve canonical name, short code or alias to one contract entry."""
        if name is None or not self.enabled:
            return None
        original = self._norm(name)
        if not original:
            return None

        candidates = [original]
        if namespace and "." not in original:
            candidates.insert(0, f"{namespace}.{original.lower()}")
        # Guardrail codes are the main compatibility use case. This fallback is
        # deliberate and does not affect arbitrary event names containing dots.
        if "." not in original:
            candidates.append(f"guardrail.{original.lower()}")

        for candidate in candidates:
            canonical = self._lookup.get(self._lookup_key(candidate))
            if canonical is not None:
                return self._entries.get(canonical)
        return None

    def map(self, code: str | None) -> str | None:
        if code is None or not self.enabled:
            return code
        original = self._norm(code)
        entry = self.resolve(original)
        return entry.label if entry and entry.label else original

    def action_for(self, code: str | None, *, namespace: str = "guardrail") -> str | None:
        """Return declarative guardrail action, if the contract defines one."""
        entry = self.resolve(code, namespace=namespace)
        return entry.action if entry else None

    def remediation_for(self, code: str | None, *, namespace: str = "guardrail") -> dict[str, Any] | None:
        """Return declarative remediation metadata for a rail, if configured."""
        entry = self.resolve(code, namespace=namespace)
        if not entry:
            return None
        raw = entry.metadata.get("remediation") if isinstance(entry.metadata, Mapping) else None
        if isinstance(raw, str):
            return {"type": raw}
        if isinstance(raw, dict):
            return dict(raw)
        return None

    def normalize_name(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        original = self._norm(name)
        mapped = self._norm(self.map(original) or original)
        meta = dict(metadata or {})
        if mapped != original:
            meta.setdefault("observability_name_internal", original)
            meta.setdefault("observability_name_mapped", mapped)
            meta.setdefault("observability_code_mapped", True)
        return mapped, meta

    def normalize_payload(
        self,
        code: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        original = self._norm(code)
        mapped = self._norm(self.map(original) or original)
        body = dict(payload or {})
        meta = dict(metadata or {})
        if mapped != original:
            body.setdefault("event_code_internal", original)
            meta.setdefault("event_code_internal", original)
            meta.setdefault("event_code_mapped", mapped)
            meta.setdefault("observability_code_mapped", True)
        return mapped, body, meta

    @property
    def mappings(self) -> dict[str, str]:
        """Legacy view containing only entries that actually map to a label."""
        return {
            name: entry.label
            for name, entry in self._entries.items()
            if entry.label is not None
        }

    @property
    def entries(self) -> dict[str, ObservabilityMappingEntry]:
        return dict(self._entries)



def _load_mapping_document(path: str | Path | None) -> tuple[dict[str, Any], Path | None]:
    """Load a mapping document using the same project-aware path resolution as v1."""
    if not path:
        return {}, None
    requested_path = Path(path).expanduser()
    candidates: list[Path] = [requested_path]
    if not requested_path.is_absolute():
        candidates.append(Path.cwd() / requested_path)
        for root in sys.path:
            if root:
                candidates.append(Path(root).expanduser() / requested_path)
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except Exception:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if not candidate.exists():
            continue
        try:
            raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.exception("observability.mapping_file_invalid path=%s", candidate)
            return {}, candidate
        mappings = raw.get("mappings", raw) if isinstance(raw, dict) else {}
        if not isinstance(mappings, dict):
            logger.warning("observability.mapping_invalid_shape path=%s", candidate)
            return {}, candidate
        return dict(mappings), candidate
    logger.warning(
        "observability.mapping_file_not_found path=%s cwd=%s candidates=%s",
        requested_path, Path.cwd(), list(seen),
    )
    return {}, None


def _discover_agent_overlay_path(explicit_path: str | Path | None = None) -> Path | None:
    """Resolve the embedding agent's observability overlay.

    Resolution order:
      1. Explicit OBSERVABILITY_CODE_MAPPING_PATH, when supplied.
      2. ``config/observability_mapping.yaml`` under cwd/import roots.

    The framework's own packaged default file is explicitly excluded from auto
    discovery. This makes agent overlays work even when an older launcher does
    not know the OBSERVABILITY_CODE_MAPPING_* settings, while preserving the
    framework-only compatibility registry when no agent overlay exists.
    """
    default_resolved = DEFAULT_OBSERVABILITY_MAPPING_PATH.resolve()
    requested: list[Path] = []
    if explicit_path:
        raw = Path(explicit_path).expanduser()
        requested.append(raw)
        if not raw.is_absolute():
            requested.append(Path.cwd() / raw)
            for root in sys.path:
                if root:
                    requested.append(Path(root).expanduser() / raw)
    else:
        requested.append(Path.cwd() / "config" / "observability_mapping.yaml")
        for root in sys.path:
            if root:
                requested.append(Path(root).expanduser() / "config" / "observability_mapping.yaml")

    seen: set[str] = set()
    for candidate in requested:
        try:
            resolved = candidate.resolve()
            key = str(resolved)
        except Exception:
            resolved = candidate
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if resolved == default_resolved:
            continue
        if candidate.exists():
            return candidate
    return None


def create_observability_code_mapper(settings: Any | None = None) -> ObservabilityCodeMapper:
    """Build one effective observability contract registry.

    The default framework registry and the agent overlay are *merged before any
    resolution*. This is critical: the default must never first translate
    ``guardrail.dlex_in`` to ``GRL.DLEX_IN`` and only afterwards attempt the
    agent overlay. The effective registry is rebuilt once, including aliases, so
    an agent override wins for canonical names and aliases alike.

    Compatibility model:
      1. Framework default registry is loaded by default.
      2. Agent overlay is auto-discovered at ``config/observability_mapping.yaml``
         or loaded from OBSERVABILITY_CODE_MAPPING_PATH.
      3. Explicit ``OBSERVABILITY_CODE_MAPPING_ENABLED=false`` only disables an
         explicit path when the embedding settings deliberately provide both
         fields; conventional auto-discovery remains enabled for compatibility.
      4. Old agents with no overlay retain the framework historical behavior.
    """
    if settings is None:
        from agent_framework.config.settings import settings as default_settings
        settings = default_settings

    default_enabled = bool(getattr(settings, "OBSERVABILITY_DEFAULT_MAPPING_ENABLED", True))
    default_path = getattr(settings, "OBSERVABILITY_DEFAULT_MAPPING_PATH", None) or DEFAULT_OBSERVABILITY_MAPPING_PATH
    base: dict[str, Any] = {}
    base_file: Path | None = None
    if default_enabled:
        base, base_file = _load_mapping_document(default_path)

    configured_path = getattr(settings, "OBSERVABILITY_CODE_MAPPING_PATH", None)
    configured_enabled = bool(getattr(settings, "OBSERVABILITY_CODE_MAPPING_ENABLED", False))

    # If a path was explicitly configured, honour ENABLED. Without an explicit
    # path, discover the conventional agent file automatically. This means a
    # project can adopt the new framework without changing its launcher/settings.
    overlay_candidate: Path | None
    if configured_path:
        overlay_candidate = _discover_agent_overlay_path(configured_path) if configured_enabled else None
    else:
        overlay_candidate = _discover_agent_overlay_path(None)

    overlay: dict[str, Any] = {}
    overlay_file: Path | None = None
    if overlay_candidate is not None:
        overlay, overlay_file = _load_mapping_document(overlay_candidate)

    # Merge first, resolve once. Agent canonical entries fully replace the
    # framework entry with the same canonical key. Rebuilding one mapper after
    # the merge also rebuilds aliases from the winning entry, preventing stale
    # default aliases from resolving to the old label.
    effective = dict(base)
    effective.update(overlay)
    mapper = ObservabilityCodeMapper(effective, enabled=True)
    logger.info(
        "observability.mapping_registry_loaded default_enabled=%s default_path=%s "
        "default_entries=%d overlay_configured=%s overlay_path=%s overlay_entries=%d effective_entries=%d "
        "sample_dlex_in=%s sample_tox=%s",
        default_enabled,
        str(base_file.resolve()) if base_file else None,
        len(base),
        bool(configured_path),
        str(overlay_file.resolve()) if overlay_file else None,
        len(overlay),
        len(mapper.entries),
        mapper.map("guardrail.dlex_in"),
        mapper.map("guardrail.tox"),
    )
    return mapper

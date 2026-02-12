from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


ANCHOR_SUBPATH = Path("docs") / "reports" / "final-run"
REQUIRED_ANCHOR_PATHS = (
    Path("pre_batch_results.tsv"),
    Path("batch_results.tsv"),
    Path("batch_resume_from_dkt003_results.tsv"),
    Path("run_evidence_index.tsv"),
    Path("run_evidence_index.md"),
    Path("evidence_manifest.sha256"),
    Path("evidence"),
    Path("RELEASE_SNAPSHOT.md"),
)
REQUIRED_INDEX_COLUMNS = (
    "task_id",
    "run_id",
    "ledger_source",
    "execution_track",
    "evidence_complete",
    "final_assessment",
    "report_md",
    "verification_log",
    "audit_summary",
)


class BundleCommandError(Exception):
    def __init__(self, code: str, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def generate_bundle(
    *,
    root: Path,
    source_dir: str,
    bundle_root: str,
    summary_json: str,
) -> dict[str, Any]:
    source_root = _resolve_path(root, source_dir)
    if not source_root.exists() or not source_root.is_dir():
        raise BundleCommandError(
            "E_BUNDLE_SOURCE_MISSING",
            f"bundle source directory does not exist: {source_root}",
        )

    bundle_base = _resolve_path(root, bundle_root)
    anchor_destination = bundle_base / ANCHOR_SUBPATH

    if anchor_destination.exists():
        shutil.rmtree(anchor_destination)
    anchor_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, anchor_destination)

    files = sorted(
        path for path in anchor_destination.rglob("*") if path.is_file()
    )
    file_records = [
        {
            "path": path.relative_to(bundle_base).as_posix(),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in files
    ]
    reproducibility_digest = hashlib.sha256(
        "".join(
            f"{item['path']}|{item['sha256']}|{item['size_bytes']}\n"
            for item in file_records
        ).encode("utf-8")
    ).hexdigest()

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "workflow": "bundle-generate",
        "status": "passed",
        "root": str(root),
        "source_dir": _display_path(source_root, root),
        "bundle_root": _display_path(bundle_base, root),
        "anchor_path": str(anchor_destination.relative_to(bundle_base)),
        "file_count": len(file_records),
        "reproducibility_digest": reproducibility_digest,
        "files": file_records,
    }
    _write_summary(_resolve_path(root, summary_json), payload)
    return payload


def review_bundle(
    *,
    root: Path,
    bundle_root: str,
    summary_json: str,
) -> dict[str, Any]:
    bundle_base = _resolve_path(root, bundle_root)
    anchor_root = _resolve_anchor_root(bundle_base)

    files = sorted(path for path in anchor_root.rglob("*") if path.is_file())
    manifest_entries, malformed_lines = _read_manifest_entries(anchor_root / "evidence_manifest.sha256")
    verification_logs = sorted((anchor_root / "evidence").rglob("verification.log"))

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "workflow": "bundle-review",
        "status": "passed" if not malformed_lines else "failed",
        "bundle_root": str(bundle_base),
        "anchor_path": str(anchor_root),
        "file_count": len(files),
        "manifest_entries": len(manifest_entries),
        "verification_logs": len(verification_logs),
        "malformed_manifest_lines": malformed_lines,
    }
    _write_summary(_resolve_path(root, summary_json), payload)
    return payload


def reverify_bundle(
    *,
    root: Path,
    bundle_root: str,
    summary_json: str,
) -> tuple[int, dict[str, Any]]:
    bundle_base = _resolve_path(root, bundle_root)
    anchor_root = _resolve_anchor_root(bundle_base)

    missing_required_paths = [
        relative.as_posix()
        for relative in REQUIRED_ANCHOR_PATHS
        if not (anchor_root / relative).exists()
    ]

    index_header = _load_index_header(anchor_root / "run_evidence_index.tsv")
    index_header_matches = tuple(index_header) == REQUIRED_INDEX_COLUMNS

    manifest_entries, malformed_manifest_lines = _read_manifest_entries(anchor_root / "evidence_manifest.sha256")
    manifest_missing_paths: list[str] = []
    manifest_mismatches: list[dict[str, str]] = []
    for expected_digest, manifest_path in manifest_entries:
        resolved = _resolve_manifest_entry(
            manifest_path=manifest_path,
            bundle_base=bundle_base,
            anchor_root=anchor_root,
        )
        if not resolved.exists() or not resolved.is_file():
            manifest_missing_paths.append(manifest_path)
            continue
        observed = _sha256(resolved)
        if observed != expected_digest:
            manifest_mismatches.append(
                {
                    "path": manifest_path,
                    "expected_sha256": expected_digest,
                    "observed_sha256": observed,
                }
            )

    verification_logs = sorted((anchor_root / "evidence").rglob("verification.log"))
    command_marker_missing = [
        path.relative_to(anchor_root).as_posix()
        for path in verification_logs
        if not _has_command_markers(path)
    ]

    status = "passed"
    if (
        missing_required_paths
        or not index_header_matches
        or malformed_manifest_lines
        or manifest_missing_paths
        or manifest_mismatches
        or not verification_logs
        or command_marker_missing
    ):
        status = "failed"

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "workflow": "bundle-reverify",
        "status": status,
        "bundle_root": str(bundle_base),
        "anchor_path": str(anchor_root),
        "required_paths_missing": missing_required_paths,
        "run_evidence_index_header": index_header,
        "run_evidence_index_header_matches": index_header_matches,
        "manifest_entries_checked": len(manifest_entries),
        "malformed_manifest_lines": malformed_manifest_lines,
        "manifest_missing_paths": manifest_missing_paths,
        "manifest_mismatches": manifest_mismatches,
        "verification_logs_checked": len(verification_logs),
        "verification_logs_missing_command_markers": command_marker_missing,
    }
    _write_summary(_resolve_path(root, summary_json), payload)
    return (0 if status == "passed" else 2), payload


def _resolve_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _resolve_anchor_root(bundle_base: Path) -> Path:
    anchored = bundle_base / ANCHOR_SUBPATH
    if anchored.exists() and anchored.is_dir():
        return anchored
    if (bundle_base / "run_evidence_index.tsv").exists():
        return bundle_base
    raise BundleCommandError(
        "E_BUNDLE_ANCHOR_MISSING",
        (
            "unable to locate bundle anchor at "
            f"{bundle_base / ANCHOR_SUBPATH} or {bundle_base}"
        ),
    )


def _read_manifest_entries(manifest_path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    if not manifest_path.exists() or not manifest_path.is_file():
        return [], [f"missing:{manifest_path.name}"]

    entries: list[tuple[str, str]] = []
    malformed: list[str] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("  ", maxsplit=1)
        if len(parts) != 2:
            malformed.append(stripped)
            continue
        digest, path_text = parts[0].strip(), parts[1].strip()
        if not digest or not path_text:
            malformed.append(stripped)
            continue
        entries.append((digest, path_text))
    return entries, malformed


def _resolve_manifest_entry(*, manifest_path: str, bundle_base: Path, anchor_root: Path) -> Path:
    raw = Path(manifest_path)
    if raw.is_absolute():
        return raw

    prefix = ANCHOR_SUBPATH.parts
    if len(raw.parts) >= len(prefix) and tuple(raw.parts[: len(prefix)]) == prefix:
        anchored_candidate = bundle_base / raw
        if anchored_candidate.exists():
            return anchored_candidate
        trimmed = Path(*raw.parts[len(prefix) :])
        return anchor_root / trimmed

    anchor_candidate = anchor_root / raw
    if anchor_candidate.exists():
        return anchor_candidate
    return bundle_base / raw


def _load_index_header(index_path: Path) -> list[str]:
    if not index_path.exists() or not index_path.is_file():
        return []
    lines = index_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    return lines[0].split("\t")


def _write_summary(summary_path: Path, payload: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 64)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _has_command_markers(log_path: Path) -> bool:
    text = log_path.read_text(encoding="utf-8")
    return "Command:" in text or "=== COMMAND ENTRY" in text

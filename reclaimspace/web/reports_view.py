"""Human-readable report views for the web UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def path_size(path_str: str) -> int:
    path = Path(path_str)
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def report_summary(report: Mapping[str, object]) -> Dict[str, Any]:
    groups = report.get("groups") or []
    reclaimable_bytes = 0
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue
            candidates = group.get("candidate_paths") or []
            if isinstance(candidates, list):
                for candidate in candidates:
                    reclaimable_bytes += path_size(str(candidate))

    candidate_count = int(report.get("candidate_count") or 0)
    return {
        "ready_count": int(report.get("ready_count") or 0),
        "candidate_count": candidate_count,
        "protected_count": _protected_count(report, groups),
        "needs_review_count": int(report.get("needs_review_count") or 0),
        "quarantined_count": int(report.get("quarantined_count") or 0),
        "missing_source_count": int(report.get("missing_source_count") or 0),
        "media_type": report.get("media_type"),
        "scan_mode": report.get("scan_mode"),
        "reclaimable_bytes": reclaimable_bytes,
        "reclaimable_human": format_bytes(reclaimable_bytes),
        "summary_line": _summary_line(candidate_count, reclaimable_bytes),
    }


def _protected_count(report: Mapping[str, object], groups: object) -> int:
    """Use the stored count, or derive it so older reports still show the chip."""
    if "protected_count" in report and report.get("protected_count") is not None:
        return int(report.get("protected_count") or 0)
    if not isinstance(groups, list):
        return 0
    return sum(
        1
        for group in groups
        if isinstance(group, dict) and group.get("status") == "protected"
    )


def _path_strings(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(path) for path in value if path]


def _summary_line(candidate_count: int, reclaimable_bytes: int) -> str:
    if candidate_count == 0:
        return "No duplicate files ready to quarantine."
    size_part = format_bytes(reclaimable_bytes) if reclaimable_bytes else "unknown size"
    return f"Up to {candidate_count} files (~{size_part}) could be reclaimed."


def report_groups_table(
    report: Mapping[str, object],
    *,
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    groups = report.get("groups") or []
    rows: List[Dict[str, Any]] = []
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue
            status = str(group.get("status") or "")
            if status_filter and status != status_filter:
                continue
            candidate_list = _path_strings(group.get("candidate_paths"))
            reclaim_bytes = sum(path_size(path) for path in candidate_list)
            protected = _path_strings(group.get("protected_paths"))
            plex_paths = _path_strings(group.get("plex_paths"))
            rows.append(
                {
                    "title": group.get("title"),
                    "year": group.get("year"),
                    "rating_key": group.get("rating_key"),
                    "status": status,
                    "reason": group.get("reason"),
                    "candidate_count": len(candidate_list),
                    "reclaimable_bytes": reclaim_bytes,
                    "reclaimable_human": format_bytes(reclaim_bytes),
                    "plex_paths": plex_paths,
                    "protected_paths": protected,
                    "candidate_paths": candidate_list,
                    "protected_path": protected[0] if protected else None,
                    "sample_candidate": candidate_list[0] if candidate_list else None,
                }
            )

    total = len(rows)
    page = rows[offset : offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "groups": page}

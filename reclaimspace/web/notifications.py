"""Optional webhook notifications when scans finish."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Mapping

from reclaimspace.config_store import Settings


def notify_scan_complete(
    settings: Settings,
    media_type: str,
    mode: str,
    summary: Mapping[str, object],
    report_name: str,
    *,
    failed: bool = False,
    error: str = "",
) -> None:
    webhook = (settings.notification_webhook_url or "").strip()
    if not webhook:
        return

    status = "failed" if failed else "completed"
    text = (
        f"Reclaimspace scan {status}: {media_type} ({mode})\n"
        f"Report: {report_name}\n"
        f"Ready: {summary.get('ready_count', 0)}, "
        f"Candidates: {summary.get('candidate_count', 0)}"
    )
    if failed and error:
        text += f"\nError: {error}"

    payload = {"content": text, "text": text, "message": text}
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except (urllib.error.URLError, TimeoutError):
        pass

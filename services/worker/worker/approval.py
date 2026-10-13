"""Fail-closed engineering review metadata for frozen benchmark criteria."""

import hashlib
import hmac
import json
import re
from datetime import date
from typing import Any


def criteria_sha256(manifest: dict[str, Any]) -> str:
    """Bind a review to all benchmark fields except the review record itself."""
    criteria = {key: value for key, value in manifest.items() if key != "reviewer_signoff"}
    encoded = json.dumps(criteria, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def require_benchmark_approval(manifest: dict[str, Any], development: bool) -> bool:
    """Return acceptance eligibility; explicit diagnostics never become acceptance."""
    if development:
        return False
    signoff = manifest.get("reviewer_signoff")
    if not isinstance(signoff, dict):
        raise ValueError("Engineering-owner review pending or invalid; use DEVELOPMENT=1")
    reviewer = signoff.get("reviewer")
    reviewed_on = signoff.get("reviewed_on")
    digest = signoff.get("criteria_sha256")
    if (
        signoff.get("disposition") != "APPROVED"
        or not isinstance(reviewer, str)
        or not reviewer.strip()
        or reviewer.strip().upper().startswith("PENDING")
        or not isinstance(reviewed_on, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed_on)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise ValueError("Engineering-owner review pending or invalid; use DEVELOPMENT=1")
    try:
        date.fromisoformat(reviewed_on)
        expected = criteria_sha256(manifest)
    except (ValueError, TypeError) as error:
        raise ValueError("Engineering-owner review metadata is invalid") from error
    if not hmac.compare_digest(digest, expected):
        raise ValueError("Engineering-owner review is stale for these benchmark criteria")
    return True

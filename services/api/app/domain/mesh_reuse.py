"""Exact physical mesh contract; analysis name/material/loading do not change connectivity."""

import hashlib
from typing import Any

from app.domain.deck_service import canonical
from app.domain.loads import DeckSnapshot


def physical_controls(snapshot: DeckSnapshot) -> dict[str, Any]:
    setup = snapshot.mesh_setup
    return {
        "global_size_m": setup.global_size_m,
        "curvature_elements": setup.curvature_elements,
        "local_sizes": sorted((s.kind, s.entity_id, s.size_m) for s in setup.local_sizes),
    }


def compatibility_hash(snapshot: DeckSnapshot, policy: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical(
            {
                "schema": 1,
                "geometry": snapshot.geometry.model_dump(mode="json"),
                "controls": physical_controls(snapshot),
                "policy": policy,
            }
        )
    ).hexdigest()

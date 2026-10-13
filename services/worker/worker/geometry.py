"""Fail-closed, revision-bound matching of planar synthetic CAD faces."""

from typing import Any


def match_faces(
    catalog: dict[str, Any], imported: list[dict[str, Any]], revision: str
) -> dict[str, int]:
    if catalog["revision"] != revision:
        raise ValueError("Unresolved: stale geometry revision")
    faces = catalog["faces"]
    if len({f["id"] for f in faces}) != len(faces):
        raise ValueError("Unresolved: duplicate immutable face IDs")
    if len({f["tag"] for f in imported}) != len(imported):
        raise ValueError("Unresolved: duplicate transient surface tags")
    candidates: dict[str, list[int]] = {}
    for face in faces:
        candidates[face["id"]] = [
            item["tag"]
            for item in imported
            if item["body"] == face["body"]
            and abs(item["area"] - face["area"]) <= 1e-8
            and all(
                abs(a - b) <= 1e-6
                for key in ("center", "bounds")
                for a, b in zip(item[key], face[key], strict=True)
            )
        ]
    if len(faces) != len(imported) or any(len(v) != 1 for v in candidates.values()):
        raise ValueError("Unresolved: missing or ambiguous face signature; no proximity guess")
    mapping = {key: value[0] for key, value in candidates.items()}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Unresolved: mapping is not one-to-one")
    by_tag = {item["tag"]: item for item in imported}
    for face in faces:
        if {mapping[n] for n in face["neighbors"]} != set(by_tag[mapping[face["id"]]]["neighbors"]):
            raise ValueError("Unresolved: face adjacency mismatch")
    return mapping

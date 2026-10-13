"""Real copy-based edits, restored face mapping and controlled resource termination."""

import json
from pathlib import Path

import pytest

from worker.cleanup import cleanup_fixture, cleanup_preview
from worker.resources import measured_native
from worker.runtime import NATIVE, NativeOperationError, quadratic_mesh, sha256


@pytest.mark.parametrize("kind", ["hole", "fillet"])
def test_native_cleanup_preview_preserves_original_and_remeshes(kind: str, tmp_path: Path) -> None:
    source = tmp_path / "source"
    catalog = cleanup_fixture(source, kind)  # type: ignore[arg-type]
    hashes = {p.name: sha256(p) for p in source.iterdir()}
    selected = next(f["id"] for f in catalog["faces"] if f["surface"] == "cylinder")
    preview = tmp_path / "preview"
    edit = cleanup_preview(source, preview, selected)
    assert edit["volume_delta_m3"] == pytest.approx(edit["expected_delta_m3"], abs=1e-10)
    assert edit["preview_volume_m3"] == pytest.approx(1, abs=1e-10)
    assert edit["source_revision"] != edit["preview_revision"]
    assert hashes == {p.name: sha256(p) for p in source.iterdir()}
    quadratic_mesh(preview, 0.6, 9000)
    mesh = json.loads((preview / "mesh.json").read_text())
    assert mesh["revision"] == edit["preview_revision"]
    assert len(mesh["face_tags"]) == 6 and mesh["elements"]
    for index, ref in enumerate(["stale:b1:f1", catalog["faces"][0]["id"]]):
        if ref == selected:
            ref = next(f["id"] for f in catalog["faces"] if f["surface"] == "plane")
        with pytest.raises(NativeOperationError):
            cleanup_preview(source, tmp_path / f"invalid-{index}", ref)
        assert hashes == {p.name: sha256(p) for p in source.iterdir()}
        assert not (tmp_path / f"invalid-{index}" / "geometry.brep").exists()


def test_resource_watchdog_stops_real_memory_growth_before_native_as_limit(tmp_path: Path) -> None:
    # Trusted diagnostic allocates 16 MiB every 20 ms, without approaching host OOM.
    script = tmp_path / "allocation.py"
    script.write_text(
        "import time\na=[]\nfor _ in range(64):\n"
        " a.append(bytearray(16*1024**2))\n time.sleep(.02)\n"
    )
    result = measured_native(
        [str(NATIVE / "venvs/mesh/bin/python"), "-I", str(script)],
        tmp_path,
        "memory-stop",
        rss_mib=128,
    )
    assert result["status"] == "rss_budget_exceeded"
    assert result["returncode"] != 0
    assert 128 * 1024**2 < result["sampled_tree_peak_rss_bytes"] < 512 * 1024**2


def test_resource_watchdog_stops_disk_growth(tmp_path: Path) -> None:
    script = tmp_path / "disk.py"
    script.write_text(
        "import time\nwith open('growth', 'wb') as f:\n"
        " for _ in range(32):\n  f.write(bytes(1024**2)); f.flush(); time.sleep(.02)\n"
    )
    result = measured_native(
        [str(NATIVE / "venvs/mesh/bin/python"), "-I", str(script)],
        tmp_path,
        "disk-stop",
        disk_mib=1,
    )
    assert result["status"] == "disk_budget_exceeded" and result["returncode"] != 0

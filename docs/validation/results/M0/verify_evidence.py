"""Read-only M0 retained-source and analytical-reference audit."""

import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path.cwd()
checks = []


def raw(path):
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def check(path, digest, label):
    actual = hashlib.sha256(raw(path)).hexdigest()
    assert actual == digest, (label, path, actual, digest)
    checks.append({"label": label, "path": str(path), "sha256": actual})


for case in ["B01", "B02"]:
    p = Path("docs/validation/results/T003") / case
    r = json.loads((p / "result.json").read_text())
    check(p / "manifest.json", r["manifest_sha256"], case + " frozen manifest")
    check(
        Path("tests/benchmarks") / (case + ".json"),
        r["manifest_sha256"],
        case + " current manifest unchanged",
    )
    for i, run in enumerate(r["runs"], 1):
        for filename, field in [("analysis.inp", "deck_sha256"), ("analysis.dat", "dat_sha256")]:
            check(p / f"mesh{i}" / filename, run[field], case + " " + field)

p = Path("docs/validation/results/T004/B09")
r = json.loads((p / "result.json").read_text())
check(p / "manifest.json", r["manifest_sha256"], "B09 frozen manifest")
check(Path("tests/benchmarks/B09.json"), r["manifest_sha256"], "B09 current manifest unchanged")
for name, filename in [("deck", "analysis.inp"), ("dat", "analysis.dat"), ("frd", "analysis.frd")]:
    check(p / filename, r["source_sha256"][name], "B09 " + name)
check(p / "stress.json", r["stress_json_sha256"], "B09 field data")

p = Path("docs/validation/results/T005")
r = json.loads((p / "B07-result.json").read_text())
check(p / "B07-mortar.json", r["manifest_sha256"], "B07 mortar frozen manifest")
check(
    Path("tests/benchmarks/B07-mortar.json"),
    r["manifest_sha256"],
    "B07 mortar current manifest unchanged",
)
for name, case in [("monolithic", r["reference"]), *r["bonded_cases"].items()]:
    print(name, [k for k in case if "sha256" in k or "audit" in k])
    for field, filename in [
        ("deck_sha256", "analysis.inp.gz"),
        ("dat_sha256", "analysis.dat.gz"),
        ("frd_sha256", "analysis.frd.gz"),
    ]:
        if field in case:
            check(p / name / filename, case[field], "B07 " + name + " " + field)

references = []
for case in ["B01", "B02", "B07-mortar", "B09"]:
    m = json.loads((Path("tests/benchmarks") / (case + ".json")).read_text())
    if case == "B01":
        e = m["material"]["E_pa"]
        nu = m["material"]["nu"]
        g = m["displacement_gradient"]
        eps = [[(g[i][j] + g[j][i]) / 2 for j in range(3)] for i in range(3)]
        mu = e / (2 * (1 + nu))
        lam = e * nu / ((1 + nu) * (1 - 2 * nu))
        trace = sum(eps[i][i] for i in range(3))
        s = [
            [2 * mu * eps[i][j] + (lam * trace if i == j else 0) for j in range(3)]
            for i in range(3)
        ]
        values = [s[0][0], s[1][1], s[2][2], s[0][1], s[0][2], s[1][2]]
        assert all(
            math.isclose(v, ref, abs_tol=1e-7, rel_tol=1e-14)
            for v, ref in zip(values, m["expected_stress_ccx_pa"], strict=True)
        )
        references.append({"case": case, "independent_hooke_stress_ccx_pa": values})
    elif case == "B02":
        force = m["total_force_n"][0]
        values = [force, 0, 0, 0, 0, 0]
        assert values == m["expected_stress_ccx_pa"]
        references.append(
            {
                "case": case,
                "expected_end_ux_m": force / m["material"]["E_pa"],
                "stress_pa": force,
                "area_m2": 1,
                "length_m": 1,
            }
        )
    elif case == "B07-mortar":
        expected = 1e6 * 2 / m["material"]["E_pa"]
        assert math.isclose(expected, m["expected_end_ux_m"], rel_tol=1e-14)
        assert m["expected_canonical_stress_pa"] == [1e6, 0, 0, 0, 0, 0]
        references.append(
            {
                "case": case,
                "expected_end_ux_m": expected,
                "stress_pa": 1e6,
                "area_m2": 1,
                "length_m": 2,
            }
        )
    else:
        for material, data in m["materials"].items():
            expected = [data["E_pa"] * m["axial_strain"], 0, 0, 0, 0, 0]
            assert expected == m["expected_canonical_stress_pa"][material]
        references.append(
            {
                "case": case,
                "stress_pa": [210e6, 70e6],
                "interface_normal": "z",
                "interface_tractions_pa": [0, 0, 0],
                "assessment": (
                    "Tangential normal-stress jump with zero interface traction "
                    "is physically consistent; "
                    "sampling and tolerances still require owner approval"
                ),
            }
        )

report = {
    "status": "PASS read-only evidence/math audit; not engineering approval",
    "checked_sources": checks,
    "analytical_references": references,
}
Path(".local/reviews/M0/evidence-reference-audit.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
print(
    len(checks),
    "retained-source/current-manifest hashes match; "
    "four independent physical-reference checks match",
)

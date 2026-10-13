"""Provision verified, workspace-local native tools without modifying system packages."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / ".local/native"
LOCK = ROOT / "scripts/native/toolchain-lock.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: Path, log: Path) -> None:
    with log.open("ab") as output:
        subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, check=True)


def main() -> int:
    lock: dict[str, Any] = json.loads(LOCK.read_text())
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Native toolchain currently requires Linux x86_64")
    for executable in ("gcc", "ar", "make", "dpkg-deb", "uv"):
        if not shutil.which(executable):
            raise RuntimeError(f"Missing native build prerequisite: {executable}")
    compiler = subprocess.check_output(["gcc", "-dumpfullversion"], text=True).strip()
    if compiler != lock["gcc_version"]:
        raise RuntimeError(f"CCX build requires GCC {lock['gcc_version']}; found {compiler}")
    NATIVE.mkdir(parents=True, exist_ok=True)
    cache = NATIVE / "downloads"
    cache.mkdir(exist_ok=True)
    for artifact in lock["artifacts"]:
        destination = cache / artifact["name"]
        if not destination.exists():
            # TLS defaults and the reviewed artifact digest are mandatory.
            temporary = destination.with_suffix(destination.suffix + ".partial")
            try:
                with urllib.request.urlopen(artifact["url"], timeout=60) as response:
                    with temporary.open("wb") as output:
                        shutil.copyfileobj(response, output)
                if digest(temporary) != artifact["sha256"]:
                    raise RuntimeError(f"Artifact checksum mismatch: {artifact['name']}")
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        if digest(destination) != artifact["sha256"]:
            raise RuntimeError(f"Cached artifact checksum mismatch: {artifact['name']}")
    for component in ("cad", "mesh", "post"):
        environment = os.environ | {
            "UV_PROJECT_ENVIRONMENT": str(NATIVE / "venvs" / component),
        }
        subprocess.run(
            [
                "uv",
                "sync",
                "--locked",
                "--project",
                str(ROOT / "services/worker/environments" / component),
                "--python",
                (ROOT / ".python-version").read_text().strip(),
            ],
            env=environment,
            cwd=ROOT,
            check=True,
        )
    bins = NATIVE / "bin"
    bins.mkdir(exist_ok=True)
    manifest = NATIVE / "build.json"
    build_inputs = hashlib.sha256(
        LOCK.read_bytes()
        + Path(__file__).read_bytes()
        + (ROOT / "scripts/native/netdeny.c").read_bytes()
        + subprocess.check_output(["gcc", "--version"])
        + subprocess.check_output(["ar", "--version"])
    ).hexdigest()
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        if previous["inputs_sha256"] == build_inputs and all(
            Path(NATIVE / filename).is_file() and digest(NATIVE / filename) == expected
            for filename, expected in previous["outputs_sha256"].items()
        ):
            print("Native build reused: source/toolchain/launcher inputs and output hashes match")
            return 0
    sysroot = NATIVE / "sysroot"
    sysroot.mkdir(exist_ok=True)
    for artifact in lock["artifacts"]:
        if artifact["kind"] == "debian":
            subprocess.run(
                ["dpkg-deb", "-x", str(cache / artifact["name"]), str(sysroot)], check=True
            )
    build = NATIVE / "build"
    # This directory contains only generated copies owned by this installer.
    if build.exists():
        shutil.rmtree(build)
    build.mkdir()
    for name, directory in (
        ("ccx_2.23.src.tar.bz2", "ccx"),
        ("spooles.2.2.tgz", "spooles"),
        ("ccx_2.23.SPOOLEScorrection.tar.bz2", "correction"),
        ("ccx_2.23.htm.tar.bz2", "manual"),
    ):
        with tarfile.open(cache / name) as archive:
            archive.extractall(build / directory, filter="data")
    spooles = build / "spooles"
    tree_make = spooles / "Tree/src/makeGlobalLib"
    # Upstream README.INSTALL explicitly documents this source-archive filename typo.
    tree_make.write_text(tree_make.read_text().replace("drawTree.c", "draw.c"))
    correction = build / "correction/CalculiX/ccx_2.23/SPOOLES.2.2/I2Ohash/src/util.c"
    shutil.copy2(correction, spooles / "I2Ohash/src/util.c")
    log = NATIVE / "build.log"
    log.write_text("")
    # Shared spooles.a is updated by recursive makes; parallel ar writes would race.
    run(["make", "-j1", "lib", "CC=gcc", "CFLAGS=-O2 -std=gnu89"], spooles, log)
    source = build / "ccx/CalculiX/ccx_2.23/src"
    fortran = sysroot / "usr/bin/x86_64-linux-gnu-gfortran-14"
    lib = NATIVE / "lib"
    lib.mkdir(exist_ok=True)
    runtime = sysroot / "usr/lib/x86_64-linux-gnu"
    for name in ("libgfortran.so.5", "libquadmath.so.0", "libgomp.so.1", "libgcc_s.so.1"):
        shutil.copyfile(runtime / name, lib / name)
    archives = [
        spooles / "spooles.a",
        runtime / "libarpack.a",
        runtime / "lapack/liblapack.a",
        runtime / "blas/libblas.a",
    ]
    makefile = source / "Makefile.openfea"
    makefile.write_text(f"""CC=gcc
FC={fortran}
CFLAGS=-O2 -fopenmp -fcommon -Wno-error=return-mismatch -I{spooles} -DARCH=Linux
CFLAGS+=-DSPOOLES -DARPACK -DMATRIXSTORAGE
FFLAGS=-O2 -cpp -fopenmp -fallow-argument-mismatch
LIBS={" ".join(str(p) for p in archives)} -lpthread -lm
include Makefile.inc
OBJECTS=$(SCCXF:.f=.o) $(SCCXC:.c=.o)
all: ccx
%.o: %.c
\t$(CC) $(CFLAGS) -c $< -o $@
%.o: %.f
\t$(FC) $(FFLAGS) -c $< -o $@
ccx: ccx_2.23.o $(OBJECTS)
\t$(FC) -fopenmp -o $@ $^ $(LIBS) -Wl,-rpath,'$$ORIGIN/../lib'
""")
    print(
        f"Building CPU CCX 2.23 with {lock['build_jobs']} jobs; log: {log.relative_to(ROOT)}",
        flush=True,
    )
    run(["make", "-f", str(makefile), f"-j{lock['build_jobs']}"], source, log)
    shutil.copyfile(source / "ccx", bins / "ccx")
    (bins / "ccx").chmod(0o755)
    run(
        [
            "gcc",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "scripts/native/netdeny.c"),
            "-o",
            str(bins / "netdeny"),
        ],
        ROOT,
        log,
    )
    outputs = {str(p.relative_to(NATIVE)): digest(p) for p in [*bins.iterdir(), *lib.iterdir()]}
    manifest.write_text(
        json.dumps(
            {
                "inputs_sha256": build_inputs,
                "outputs_sha256": outputs,
                "ccx_version": "2.23",
                "linear_solver": "serial SPOOLES 2.2 with official CCX correction",
                "eigen_library": "ARPACK-NG 3.9.1",
                "blas_lapack": "Netlib 3.12.1",
                "integer_width_bits": 32,
                "compiler": subprocess.check_output(["gcc", "--version"], text=True).splitlines()[
                    0
                ],
                "fortran_flags": "-O2 -cpp -fopenmp -fallow-argument-mismatch",
                "c_flags": "-O2 -fopenmp -fcommon -Wno-error=return-mismatch -DARCH=Linux "
                "-DSPOOLES -DARPACK -DMATRIXSTORAGE",
            },
            indent=2,
        )
        + "\n"
    )
    print("Native CPU solver and network-denying launcher built and hashed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Known no-network wrapper; kernel child high-water RSS and CPU counters."""

import json
import resource
import signal
import subprocess
import sys
from pathlib import Path

process = subprocess.Popen(sys.argv[2:], stdin=subprocess.DEVNULL)


def terminate(_signal, _frame):
    # Parent terminates the owned group. Keep this wrapper alive to reap its direct child.
    try:
        process.send_signal(signal.SIGTERM)
    except ProcessLookupError:
        pass


signal.signal(signal.SIGTERM, terminate)
returncode = process.wait()
usage = resource.getrusage(resource.RUSAGE_CHILDREN)
Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "maxrss_bytes": usage.ru_maxrss * 1024,
            "user_seconds": usage.ru_utime,
            "system_seconds": usage.ru_stime,
            "returncode": returncode,
            "scope": "Linux child-process maximum RSS; sampled tree sum includes wrapper",
        }
    )
    + "\n"
)
raise SystemExit(returncode if returncode >= 0 else 128 - returncode)

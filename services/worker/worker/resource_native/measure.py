"""Known no-network wrapper; kernel child high-water RSS and CPU counters."""

import json
import resource
import subprocess
import sys
from pathlib import Path

result = subprocess.run(sys.argv[2:], stdin=subprocess.DEVNULL, check=False)
usage = resource.getrusage(resource.RUSAGE_CHILDREN)
Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "maxrss_bytes": usage.ru_maxrss * 1024,
            "user_seconds": usage.ru_utime,
            "system_seconds": usage.ru_stime,
            "returncode": result.returncode,
            "scope": "Linux child-process maximum RSS; sampled tree sum includes wrapper",
        }
    )
    + "\n"
)
raise SystemExit(result.returncode if result.returncode >= 0 else 128 - result.returncode)

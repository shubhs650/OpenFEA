"""Fail unless the native job process is actually denied network socket creation."""

import errno
import json
import socket

checked = []
for family, kind in (
    (socket.AF_INET, socket.SOCK_STREAM),
    (socket.AF_INET6, socket.SOCK_STREAM),
    (socket.AF_INET, socket.SOCK_DGRAM),
):
    try:
        connection = socket.socket(family, kind)
    except PermissionError as error:
        assert error.errno == errno.EPERM
        checked.append(f"{family.name}/{kind.name}")
    else:
        connection.close()
        raise RuntimeError("Native network isolation failed: socket creation succeeded")
print("OPENFEA_PROBE=" + json.dumps({"network_denied": True, "checked": checked}))

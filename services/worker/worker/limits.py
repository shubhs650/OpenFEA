"""Server-owned local envelope; retries and mesh profiles share these limits."""

JOB_SECONDS = 180
STAGE_SECONDS = 60
RSS_BYTES = 1536 * 1024**2
SCRATCH_BYTES = 192 * 1024**2
ARTIFACT_BYTES = 64 * 1024**2
FILE_BYTES = 32 * 1024**2
LOG_BYTES = 8 * 1024**2
DISK_RESERVE_BYTES = 1024**3
INFRASTRUCTURE_RETRIES = 1
LEASE_SECONDS = 10


def policy() -> dict[str, int]:
    return {
        "job_wall_seconds": JOB_SECONDS,
        "stage_wall_seconds": STAGE_SECONDS,
        "rss_bytes": RSS_BYTES,
        "scratch_bytes": SCRATCH_BYTES,
        "artifact_bytes": ARTIFACT_BYTES,
        "file_bytes": FILE_BYTES,
        "log_bytes": LOG_BYTES,
        "disk_reserve_bytes": DISK_RESERVE_BYTES,
        "automatic_retries": INFRASTRUCTURE_RETRIES,
        "lease_seconds": LEASE_SECONDS,
    }

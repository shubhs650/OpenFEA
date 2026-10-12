# Configuration contract to implement

These are proposed application environment variables, not existing scripts or Codex platform settings. T001 creates a commented `.env.example` without secrets; beta validation fails closed when mandatory settings are missing. Environment-specific configuration must never change numerical meaning silently.

| Variable | Local / development | Beta policy |
|---|---|---|
| FEA_ENV | local or test | beta; local authentication bypass forbidden |
| FEA_BIND_HOST | 127.0.0.1 | Internal bind behind TLS proxy; explicit allowed origin |
| FEA_DATABASE_URL | SQLite under configured data root | Control-host local SQLite, backup enabled |
| FEA_DATA_ROOT | Writable local non-repository data folder | Restricted control-host working directory |
| FEA_STORAGE_BACKEND | filesystem | s3 |
| FEA_AWS_REGION | unset | Validated India allowlist; candidate ap-south-1 |
| FEA_ARTIFACT_BUCKET | unset | Private same-region bucket |
| FEA_AUTH_MODE | local | google_oidc |
| FEA_GOOGLE_CLIENT_ID | unset | Operator-provisioned public client identifier |
| FEA_GOOGLE_CLIENT_SECRET | unset | Secret manager/runtime injection, never committed |
| FEA_SESSION_SECRET | Ephemeral development secret | Strong managed secret with rotation plan |
| FEA_CCX_PATH | Verified native binary | Image-pinned verified native binary |
| FEA_WORKER_PROFILE | local bounded subprocess | Measured CPU/RAM image profile |
| FEA_MAX_ACTIVE_JOBS | 1 | 1 |
| FEA_MAX_MODEL_ELEMENTS | Measured ceiling, target around 100000 | Measured ceiling per worker, not assumed |
| FEA_JOB_MEMORY_MIB | Calibrated; initially conservative | Enforced worker limit plus host reserve |
| FEA_JOB_TIMEOUT_SECONDS | Bounded development ceiling | Minimum of resource policy and cost deadline |
| FEA_RESULT_RETENTION_DAYS | 30 in retention tests | 30 |
| FEA_MONTHLY_BUDGET_INR | Synthetic test ledger | 3000 total target, with fixed-cost reserve |
| FEA_RATE_CARD_ID | synthetic-v1 | Immutable calibrated current rate-card version |

Upload bytes, archive expanded size, file count, geometry entity count, max retained storage and report/slice CPU limits also require explicit configuration after measured calibration. Tests exercise low thresholds without allocating huge resources. Do not use unlimited defaults in beta.

Secrets never appear in `make doctor` output. Log only whether a required secret is present. Separate sensitive secret settings from printable native-tool versions/resource limits. Unsupported mode/region/bucket combination blocks startup instead of falling back to public or local access.

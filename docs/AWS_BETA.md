# India-only beta deployment candidate

Status: proposed, not provisioned or price-validated. Default candidate ap-south-1. Compare ap-south-2 only if its required services and prices are suitable; both are India regions. No Spot compute for initial beta.

## Minimal topology

A small always-on Linux control VM serves static UI, API, TLS and SQLite-backed queue. A separately started/stopped CPU EC2 worker handles meshing/solving and heavy geometry/postprocessing; one heavy job at a time. Private S3 holds durable model/results/backups in the same region. Control-plane provisioning uses least-privilege instance roles. A small control VM is a candidate, not an assumed capacity: large STEP parsing runs on the worker, and all unmetered geometry operations still have quotas/time limits.
Use regional artifact access; no global CDN for private geometry/results. Avoid an always-on NAT gateway or load balancer unless measured benefits justify fixed cost. A worker may use a public subnet with no inbound ingress and controlled outbound access, or a measured-cost private endpoint topology. It never exposes solver ports. Retrieve worker bundles from a same-region registry/storage after verifying signatures/digests.
Initial worker shortlist: x86_64 CPU/RAM configurations calibrated to 25k/100k C3D10 workloads; 2–4 vCPU and 8–16 GiB are experiment candidates, not sizing guarantees. Use only tested native architecture builds. Do not select cheap ARM merely by price before validating dependency compatibility and runtime.

## Deployment prerequisites

Dated regional cost worksheet includes compute, stopped worker EBS, control disk, S3, requests, snapshots, public IPv4, logs, internet transfer, image registry if used, FX and taxes. No free-tier assumption. Confirm fixed monthly cost plus reserve leaves a useful solve pool below ₹3,000. Simulate no jobs, typical usage and runaway cutoff. Obtain actual deployment authorization once plan and cost are concrete; this docs request does not deploy.
Provision with OpenTofu: region allowlist, private encrypted buckets, public-access blocks, lifecycle rules, service roles, scoped operator role, secret storage, log retention, budget notifications and independent expiry/TTL mechanism. Version/IaC plan reviewed before apply. For a five-user beta, do not add autoscaling fleets, managed database clusters or Kubernetes.

## Residency and availability

Model bytes, native processing, metadata, screenshots/reports, logs and backups stay in India. Disable cross-region copies outside India and external telemetry carrying project data. Static code may be public, but signed private artifact URLs must not traverse an external application proxy. Google receives authentication identity data, not CAD; disclose that distinction. Repository/Codex data must be synthetic because Codex Cloud locality is not established by this AWS design.
24/7 access is a best-effort beta objective, not high-availability SLA. Control-host maintenance/outage is possible. Worker cold start is visible as provisioning. Daily backups meet up-to-one-day project-change-loss target; proposed recovery drill goal is same working day, with no unapproved formal RTO guarantee.

## Operator functions

Invite/revoke user, allocate/rebalance allowances, view aggregate usage/health, cancel/fence jobs, disable admission, reconcile credits, trigger backup/restore and retention. Application admin has no routine browse-all-projects endpoint. Infrastructure operators technically have privileged capabilities; document and audit them honestly rather than claiming cryptographic operator blindness. Troubleshooting normally uses user-created diagnostic bundles.

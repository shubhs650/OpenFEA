# Usage, reserves and spending controls

Policy: ₹3,000/month total AWS target; 3–5 users; baseline individual allowances plus operator reserve. No commercial payments in beta. Compute approval applies to meshing and solving only. Geometry import/cleanup, viewing and reporting are bounded operational work covered by disclosed overhead; storage and transfer are separately itemized in usage accounting. Initial allowances are provisional and set only after fixed costs are measured.

## Do not confuse four values

Provider cost incurred; customer-equivalent usage at rate card; credits for platform faults; remaining allowance after reservations. A credit does not erase AWS cost. Keep all four in the ledger. Store currencies with fixed precision and dated FX; disclose tax assumptions.

Cost forecast = fixed control host + disks/snapshots + IP/network + logs/requests + retained bytes + worker billed time + transfer + taxes + contingency. Available compute pool = 3000 minus forecast non-compute cost minus reserve. If <=0, beta deployment is blocked.
Example allocation method (not price quote): reserve 20% of remaining variable budget, distribute 80% equally among enrolled testers; admin may rebalance with audit trail. The percentage is a tunable proposed default, not an interview commitment.

## Estimate and admission

Use observed job classes (geometry complexity, nodes/DOFs, formulation and hardware) to return a range, confidence/unknown flag and maximum approved exposure. Until calibrated, use a conservative resource-time envelope; never invent a precise estimate. Reject jobs whose minimum provisioning/termination allowance cannot fit.
Reserve atomically against user and global remaining balances before queueing. Reservation records include hardware/rate ID, maximum time, stop margin and expiration. Revalidate on dispatch if delay changes rate/availability; changed economics require a fresh user approval. A quoted rate remains fixed for the accepted attempt.
User estimate includes disclosed worker startup allocation, billing granularity and stopping overhead where charged. Idle control infrastructure is platform overhead. Do not charge ordinary queue waiting. Cancellation pays actual consumed modeling usage, not the full reservation. Rate cards state allocation method; allocated instance time is not mislabeled CPU utilization.

## Stop enforcement

Calculate stop deadline from approved cap after provisioning, billing-rounding and shutdown margins. Server and worker independently monitor monotonic elapsed time; independent host/instance TTL guard stops runaway compute even if API dies. Bound output bytes, memory, processes and disk too. Stop before the user-facing cap; absorb any platform overrun as operator reserve/credit. Poll timing and billing delay make an absolute provider invoice ceiling impossible to guarantee; state this in operations, not as a false hard-cap claim.
Global guard stops new reservations while preserving enough forecast budget for fixed services. AWS Budgets provides secondary delayed alerts, not enforcement. Daily reconcile provider actuals against ledger; forecast remaining fixed charges before allocating more credit. A runaway service cannot be solved with alerts alone.

## Failure policy

User/model failures consume real usage; platform failure credit references original usage. Unknown cause is not auto-classified as user fault. Platform interruption allows at most one retry after old execution is fenced. Retry must fit global operator reserve and unchanged user limit; otherwise stop and explain. Mesh algorithm recovery uses initial+two attempts within the same approved mesh cap; it is distinct from one infrastructure retry. Never multiply these into unbounded retries; a per-job total time/cost budget dominates both.

## Later paid service

Itemize compute, storage and data transfer plus disclosed overhead/reserve margin. Publish rate version, billing unit, minimum allocation, failed-job policy and examples. Payment processor fees/taxes and chargeback operations need separate future design. No specific rupee compute rate is promised by this kit.

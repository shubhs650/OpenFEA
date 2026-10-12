# Copyable Codex session prompts

## Implement one task

Read AGENTS.md, PROGRESS.md, TASKS.md and docs/tasks/Txxx.md, plus its referenced specs. Confirm dependencies from repository evidence. Implement only Txxx; make routine reversible choices autonomously within the agreed scope. Run its acceptance checks, record limitations honestly, update task/progress records and prepare a reviewable PR. Do not deploy or merge. If a prerequisite is blocked, investigate and report the exact blocker instead of simulating success.

## Continue a task

Read the current task and last handoff in PROGRESS.md. Inspect the actual repository before trusting the handoff. Continue incomplete acceptance criteria without restarting completed work. Preserve unrelated changes. Run targeted tests and record the next bounded step.

## Review engineering changes

Review this branch against ENGINEERING_SPEC.md and the task acceptance criteria. Focus on dimensional consistency, C3D10/face mapping, traction resultants, constraints/tie behavior, stress provenance and benchmark validity. Reproduce applicable tests. Report concrete defects with severity and evidence; do not adjust tolerances to make the branch pass.

## Milestone gate

Audit docs/plan/Mx.md against actual implementation, tests and PROGRESS.md. Run the required gate suite. List passed, failed, skipped and not-run evidence, including scope exceptions. Update gate status only when all mandatory criteria are met. Recommend the first unblocked next task; do not claim an incomplete milestone is complete.

## Correct a defect

Reproduce the supplied issue with a minimal synthetic fixture. Identify which contract was violated, add a meaningful regression test, implement the smallest fix and verify affected benchmark cases. Update documentation only if intended behavior changes, with an ADR when needed.

## Expand a large task

Split Txxx into session-sized child tasks with goal, paths, acceptance, tests and dependencies. Preserve its scope and keep the parent incomplete until all children pass. Do not write feature code in this planning session.

## AWS readiness

Review AWS_BETA.md and COST_MODEL.md. Gather dated Indian-region rates, produce the no-jobs/typical/worst-case worksheet and validate the infrastructure plan without apply. Identify all fixed costs and residual overrun exposure. Present the concrete deployment plan and cost evidence for authorization; do not provision resources.

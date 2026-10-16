# Guided local tutorials

Open **Guided tutorials** in the model tree. Download either original synthetic STEP file, start the timer, and follow the checked steps alongside the ordinary project/import/material/load/mesh/results/report controls. Nothing in the guide applies a material, approves a bond, submits a solve or certifies a result automatically. Face-tree buttons show physical centres in metres to help identify the intended mounting and loaded ends.

The planar mounting bracket is 80 × 20 × 60 mm, E=210 GPa, nu=0.3, fixed at the top mounting end and loaded with a distributed -10 N Z force at the horizontal free end. Mesh at 8 mm then 6 mm, inspect the same interior point (40,10,7.5) mm and a volume section, compare runs, and export the report with **Include current physical refinement comparison** selected and your assumptions in the conclusion. The sharp-corner fixture is explicitly separate from offline B10's 5 mm inner fillet; curved product volume solves remain blocked. Neither model provides an analytical peak-stress target or a certified allowable.

The bonded example contains two independent unit cubes with one full zero-gap unit-square interface. Assign E=68.3 GPa and nu=0 to both, fix x=0, apply +0.001 MPa pressure at x=2 m, explicitly review/approve the connection, and mesh at 600 then 400 mm. Check actual assembly constraints before solving. Expected interior sigma_xx is -1000 Pa and tip ux is -2.92825768668e-8 m from FL/AE. This is the existing bounded mortar scope, not general contact, physical-gap, friction or multi-bond validation.

## Timing and learning logs

The tab uses a monotonic clock with mutually exclusive setup, observed compute-wait and manual-pause intervals. STEP upload/inspection, mesh/solve submission and observed nonterminal jobs for the open analysis, PDF generation and Word generation exclude time from setup. Overlapping compute sources count once. Job completion is observed by the existing one-second poll, so the conservative wait includes polling latency; this is elapsed workflow time, not CPU time. Keep the same analysis open. Pause for breaks, untracked geometry edits/export compute or work in another analysis/tab. Refreshing the page resets the clock. This prototype timer is not a spending control.

After checking every step, download the local JSON learning log: tutorial version, browser, timestamp, setup/compute/pause milliseconds, self-reported completed steps, help requests, measured values and errors. The guide stores notes in memory; it does not send them to an analytics service. Starting a new attempt resets step progress and timing; explicitly clear notes for a different tester. A checked step is a user's statement, not proof of execution.

Human usability acceptance remains a separate consented 3–5-person trial at T030: bracket setup target 30 minutes excluding compute, without live assistance; >=80% success (all for 3–4 testers, at least 4/5). Automated browser runs are regression evidence and cannot count as those participants.

See [T028 reference/evidence record](validation/T028.md) and [source selection and rights](validation/T028-sources.md).

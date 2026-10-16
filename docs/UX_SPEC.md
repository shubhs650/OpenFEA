# Workspace and interaction specification

Desktop-first English UI is a proposed baseline; no localization commitment. Target reference viewport 1366×768 and larger, functional at 1280×720. Light default; dark persisted per user. Keyboard-focusable controls, visible labels, accessible dialogs, non-color-only statuses.

## Workspace

Top bar: project/analysis name, saved state, units, help, theme and account. Left: tree for geometry, materials, bonds, mesh, loads/supports, runs and results. Center: shared viewport with fit, standard views, orientation axes, hide/isolate bodies, selection filter and legend. Right: property editor with Apply/Cancel, validation and arrow preview. Bottom: expandable job/status panel, never permanent log clutter. Guided checklist indicates not started, needs attention, ready, complete; it does not enforce arbitrary edit order.
Reserve geometry selection and solve actions for clear labeled controls; use progressive disclosure for advanced mesh parameters. Avoid copying branded icons or proprietary UI assets from ANSYS/SimScale.

## Selection and editing

Hover highlights separately from selected faces. Multi-select with visible count, removable selection chips and clear-all. Occluded faces can be reached by hide/isolate and tree selection. CAD face identity survives camera movement and tessellation LOD. Direction picks temporarily switch filters and return to face mode. Show units at every numeric input, validate on apply, and preview load magnitude/sign before saving.
Autosave indicates saving/saved/error; never imply saved before server acknowledgment. Revision conflicts present reload/duplicate options, never silently overwrite another browser tab. Undo restores command-level edits within current session. Geometry edits preview before/after and invalidate dependent mesh; show exactly which assignments need review.

## Critical flows

1. Import: select STEP -> upload progress -> processing -> units/size/body count -> validity and repair findings -> accept geometry.
2. Cleanup: pick feature faces -> preview -> show removed/modified regions -> commit/undo; unsupported feature returns actionable message.
3. Bond review: browse suggested pairs, gap/area and arrows -> confirm or reject -> unresolved coverage warning.
4. Mesh: global size + local overrides -> resource/usage estimate -> cap approval -> queued/status -> quality overlay or recovery explanation.
5. Solve: summarize model, resultant loads and blockers -> frozen estimate/cap -> queue -> logs optional -> return later to durable results.
6. Results: field/location selector, unit-aware legend, contour range reset, deformation scale visible, probe and section panel; warning banner survives field switching.
7. Refine: duplicate analysis settings with explicit mesh change -> comparison table at saved locations; no claim of convergence from one arbitrary comparison.
8. Export: select completed run and views -> report/archive preview -> download. Warn before result expiry; show expired status with rerun/import options.

## Failure copy patterns

- “This face changed after geometry cleanup. Select the intended face again before meshing.”
- “Body 2 may move freely. Review its supports or bonded connections.”
- “The approved compute allowance is nearly used. This job will stop before its spending limit.”
- “Meshing failed after 3 attempts. The original geometry is unchanged. Review highlighted small features.”
- “Stress exceeds the supplied yield strength. This linear-elastic result does not model plastic deformation.”

No false precise progress percentage: show stage, elapsed time, heartbeat and known counters. Queue position is approximate when cancellations occur. Browser closure does not cancel jobs. Cancel confirmation explains that consumed modeling compute is retained as usage.

## Usability evidence

Record tutorial version, browser, model, help requests, setup duration excluding compute and errors. Use synthetic mounting bracket then two-body bonded support. Capture consented notes, not private CAD screenshots in external analytics. Investigate task failure before adding features.

T028 implements [guided local tutorials](TUTORIALS.md) in the model tree, with original STEP downloads and self-reported versioned learning logs. Native wait intervals and manual pauses are excluded from setup; the observed queue poll can conservatively extend the wait. Checkboxes do not certify completion. Human sampling/30-minute acceptance remains T030.

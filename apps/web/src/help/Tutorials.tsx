import { useEffect, useRef, useState } from "react";
import bracket from "../../../../tests/fixtures/geometry/bracket-m.step?url";
import bond from "../../../../tests/fixtures/geometry/bond-zero-m.step?url";
import { TutorialClock } from "./clock";
import { useComputing } from "./compute";

const version = "T028-v1";
const common = [
  "Create a project, upload the downloaded STEP, inspect it, and confirm metres, dimensions and body count before accepting. Create an analysis for this geometry.",
  "Enter custom material properties; after selecting an example, use Edit as custom. Record Synthetic / Test only / 20 C reference and source ‘OpenFEA synthetic tutorial’. Confirm the properties and assumptions before Apply material. These are learning inputs, not certified allowables.",
];
const guides = {
  bracket: {
    title: "Planar mounting bracket",
    file: bracket,
    filename: "bracket-m.step",
    steps: [
      common[0] + " Expect 0.08 × 0.02 × 0.06 m and one body.",
      common[1] +
        " Enter E=210000 MPa and nu=0.3; leave yield strength blank. Assumptions: isotropic small-deformation linear elastic planar bracket.",
      "Expand Bodies and faces. Select only the top mounting end at z=60 mm (face centre x=5, y=10, z=60 mm). Save a Fixed support named Mount. Clear selection. Select the free end at x=80 mm (centre 80,10,5 mm). Choose Total force, enter X=0, Y=0, Z=-10 N, and save Tip force. Review the downward arrow and 10 N resultant, then clear selection.",
      "Set global mesh size to 8 mm and curvature elements to 0, save settings, and Generate local mesh. Review C3D10 quality and counts; choose the succeeded Checked mesh. Review the linear assumptions and Solve selected mesh. Compute waits are excluded automatically while this analysis remains open.",
      "View selected results. Inspect displacement Z and unaveraged von Mises stress; deformation scale is visual only. Probe the interior at (40,10,7.5) mm using an element that contains it. Generate a volume section through y=10 mm. Do not interpret support or sharp-corner peaks as converged stresses.",
      "Save global size 6 mm, mesh and solve again. Use run comparison with the same physical interior point and displacement quantity. Record both values and relative changes. The sharp planar tutorial has no analytical peak target; B10 separately tests a filleted geometry offline.",
      "Add a current view to report, write your assumptions and mesh comparison in the conclusion, select Include current physical refinement comparison, generate A4 PDF and download it. Optionally export editable Word and a portable project archive. Finish the learning log only after checking the downloaded report.",
    ],
  },
  bond: {
    title: "Reviewed bonded support",
    file: bond,
    filename: "bond-zero-m.step",
    steps: [
      common[0] +
        " Expect 2 × 1 × 1 m and two independent unit cubes sharing x=1 m, with zero physical gap.",
      common[1] +
        " Assign E=68300 MPa, nu=0 and no yield strength to EACH body. State synthetic axial reference in assumptions.",
      "Select the outer x=0 face, save a Fixed support, and clear selection. Select only the far x=2 m face, choose Pressure and enter +0.001 MPa (compression). Save and inspect the -1000 N X resultant. Clear selection.",
      "Inspect bond candidates and Review pair 1. Inspect master/slave roles, full unit-square interface, zero gap, coverage and warnings. Confirm the review checkbox and Approve saved bond yourself. Detection never approves a bond. Necessary support rank must be 6/6; this alone is not proof of stability.",
      "Set global mesh size to 600 mm, curvature elements 0, save, and mesh. Choose the succeeded mesh and Check assembly constraints. Confirm necessary mesh checks passed, complete trace coverage and the documented <=65 trace nodes per side limit. Review and solve.",
      "View results and select stress XX. Interior stress should be about -0.001 MPa, and tip ux about -0.0000292826 mm from FL/AE. Inspect both element sides at the interface; keep raw and derived fields distinct. No gap, friction, separation or general contact behavior is inferred.",
      "Repeat at 400 mm global size, compare the same physical quantities and interface sides, and export a report recording the bond, source properties and mesh comparison: add a view, select Include current physical refinement comparison, and write your assumptions in the conclusion. Leave unsupported physical-gap or multi-bond models blocked.",
    ],
  },
};

export function Tutorials() {
  const computing = useComputing();
  const [guide, setGuide] = useState<keyof typeof guides>("bracket");
  const [checked, setChecked] = useState<number[]>([]);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [times, setTimes] = useState({ setup: 0, compute: 0, paused: 0 });
  const clock = useRef<TutorialClock | null>(null);
  const [notes, setNotes] = useState("");
  const [help, setHelp] = useState("");
  const [log, setLog] = useState("");
  const mode = paused ? "paused" : computing ? "compute" : "setup";
  useEffect(() => {
    if (!running || !clock.current) return;
    clock.current.change(mode, performance.now());
    const timer = setInterval(
      () => setTimes(clock.current!.snapshot(performance.now())),
      250,
    );
    return () => clearInterval(timer);
  }, [mode, running]);
  useEffect(
    () => () => {
      if (log) URL.revokeObjectURL(log);
    },
    [log],
  );
  const selected = guides[guide];
  return (
    <details className="tutorials">
      <summary>Guided tutorials</summary>
      <section aria-label="Guided tutorials">
        <h2>Learn the local workflow</h2>
        <p>
          Version {version}. Original synthetic STEP examples. The planar
          bracket uses sharp corners; filleted product volume solves remain
          unsupported. Target: bracket setup within 30 minutes excluding
          compute. A learning log is self-reported, not engineering or
          human-usability acceptance.
        </p>
        <label>
          Choose tutorial
          <select
            value={guide}
            aria-label="Choose tutorial"
            disabled={running}
            onChange={(e) => {
              setGuide(e.target.value as keyof typeof guides);
              setChecked([]);
              setTimes({ setup: 0, compute: 0, paused: 0 });
              setLog("");
            }}
          >
            <option value="bracket">Planar mounting bracket</option>
            <option value="bond">Reviewed bonded support</option>
          </select>
        </label>
        <a href={selected.file} download={selected.filename}>
          Download tutorial STEP
        </a>
        <p>
          Work in this tab with the analysis open so native job waits are
          observed. Pause for breaks or untracked compute. Reloading resets the
          timer. No notes leave this browser unless you download the log; use
          synthetic data only.
        </p>
        <button
          disabled={running}
          onClick={() => {
            clock.current = new TutorialClock(
              performance.now(),
              computing ? "compute" : "setup",
            );
            setPaused(false);
            setRunning(true);
            setChecked([]);
            setLog("");
          }}
        >
          Start tutorial timer
        </button>
        <button disabled={!running} onClick={() => setPaused(!paused)}>
          {paused ? "Resume tutorial timer" : "Pause tutorial timer"}
        </button>
        <output
          aria-label="Tutorial timing"
          data-mode={running ? mode : "stopped"}
        >
          Setup {(times.setup / 1000).toFixed(1)} s · compute wait{" "}
          {(times.compute / 1000).toFixed(1)} s · paused{" "}
          {(times.paused / 1000).toFixed(1)} s
        </output>
        <ol>
          {selected.steps.map((text, index) => (
            <li key={text}>
              <label className="check">
                <input
                  type="checkbox"
                  disabled={!running}
                  checked={checked.includes(index)}
                  onChange={(e) =>
                    setChecked(
                      e.target.checked
                        ? [...checked, index]
                        : checked.filter((n) => n !== index),
                    )
                  }
                />
                {text}
              </label>
            </li>
          ))}
        </ol>
        <label>
          Help requests
          <textarea
            value={help}
            onChange={(e) => setHelp(e.target.value)}
            maxLength={4000}
          />
        </label>
        <label>
          Measured values and errors
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={8000}
          />
        </label>
        <button
          disabled={
            !running || checked.length !== selected.steps.length || computing
          }
          onClick={() => {
            const measured = clock.current!.snapshot(performance.now());
            setTimes(measured);
            setRunning(false);
            setLog(
              URL.createObjectURL(
                new Blob(
                  [
                    JSON.stringify(
                      {
                        version,
                        tutorial: selected.title,
                        browser: navigator.userAgent,
                        recorded_at: new Date().toISOString(),
                        duration_ms: measured,
                        completed_steps: checked,
                        help_requests: help,
                        measurements_and_errors: notes,
                        classification:
                          "self-reported learning log; not usability or engineering acceptance",
                      },
                      null,
                      2,
                    ),
                  ],
                  { type: "application/json" },
                ),
              ),
            );
          }}
        >
          Finish learning log
        </button>
        {log && (
          <a href={log} download={`openfea-${guide}-${version}.json`}>
            Download learning log
          </a>
        )}
      </section>
    </details>
  );
}

import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { getHealth } from "./health";
import { Workspace } from "./geometry/Workspace";
import "./style.css";

function App() {
  const [status, setStatus] = useState("Checking API…");
  useEffect(() => {
    const controller = new AbortController();
    void getHealth(controller.signal).then(
      () => setStatus("API connected"),
      () => {
        if (!controller.signal.aborted) setStatus("API unavailable");
      },
    );
    return () => controller.abort();
  }, []);
  return (
    <main>
      <header>
        <h1>FEA development</h1>
        <span role="status">{status}</span>
      </header>
      <Workspace />
      <footer>
        Geometry, materials and face loads with checked coarse mesh and local
        solve jobs. Calculated result views follow later.
      </footer>
    </main>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("Application root is missing");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

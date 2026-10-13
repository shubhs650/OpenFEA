import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { getHealth } from "./health";
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
      <h1>FEA development</h1>
      <p role="status">{status}</p>
      <p>Development health check. Analysis features are not available yet.</p>
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

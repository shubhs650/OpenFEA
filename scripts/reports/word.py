"""Private namespace entrypoint; fixed paths and trusted generated model only."""

import json
import subprocess
from pathlib import Path

from app.domain.reports import ReportModel
from worker.reports.docx import write_docx


def main() -> None:
    directory = Path("/work")
    model = ReportModel.model_validate_json((directory / "model.json").read_bytes())
    subprocess.run(["/node", "/app/word.mjs"], check=True, timeout=35)
    provenance = json.loads((directory / "provenance.json").read_bytes())
    write_docx(model, directory, provenance)


if __name__ == "__main__":
    main()

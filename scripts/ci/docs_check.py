"""Validate local Markdown links and the declared task dependency/status graph."""

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    errors: list[str] = []
    files = [*ROOT.glob("*.md"), *ROOT.joinpath("docs").rglob("*.md")]
    for path in files:
        text = path.read_text()
        # Fenced command examples are not documentation hyperlinks.
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            target = unquote(link.split("#", 1)[0])
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).exists():
                errors.append(f"{path.relative_to(ROOT)}: missing link {target}")
    rows = re.findall(
        r"\| \[(T\d{3})\]\([^)]*\) \| M\d \| [^|]+ \| ([^|]+) \| ([^|]+) \|",
        (ROOT / "TASKS.md").read_text(),
    )
    graph: dict[str, list[str]] = {}
    statuses: dict[str, str] = {}
    for task, dependencies, status in rows:
        statuses[task] = status.strip()
        graph[task] = re.findall(r"T\d{3}", dependencies)
        path = ROOT / f"docs/tasks/{task}.md"
        if not path.exists():
            errors.append(f"missing task file: {task}")
            continue
        text = path.read_text()
        declared = re.search(r"^Status: (.+)$", text, re.M)
        deps = re.search(r"^Dependencies: (.+)$", text, re.M)
        if declared is None or declared[1].strip() != status.strip():
            errors.append(f"{task}: status differs between task and index")
        if deps is None or re.findall(r"T\d{3}", deps[1]) != graph[task]:
            errors.append(f"{task}: dependencies differ between task and index")
    if len(rows) != 42 or set(graph) != {f"T{i:03d}" for i in range(1, 43)}:
        errors.append("task index must contain T001-T042 exactly once")
    progress_statuses: dict[str, str] = {}
    for first, last, status in re.findall(
        r"^(T\d{3})(?:[–-](T\d{3}))?: (NOT STARTED|IN PROGRESS|COMPLETE)",
        (ROOT / "PROGRESS.md").read_text(),
        re.M,
    ):
        for number in range(int(first[1:]), int((last or first)[1:]) + 1):
            progress_statuses[f"T{number:03d}"] = status
    if progress_statuses != statuses:
        errors.append("PROGRESS.md task status summary differs from TASKS.md")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task: str) -> None:
        if task in visiting:
            errors.append(f"dependency cycle at {task}")
            return
        if task in visited:
            return
        visiting.add(task)
        for dependency in graph.get(task, []):
            if dependency not in graph:
                errors.append(f"{task}: unknown dependency {dependency}")
            else:
                if statuses[task] == "COMPLETE" and statuses[dependency] != "COMPLETE":
                    errors.append(f"{task}: completed before dependency {dependency}")
                visit(dependency)
        visiting.remove(task)
        visited.add(task)

    for task in graph:
        visit(task)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(files)} Markdown files; {len(graph)} task statuses and acyclic dependencies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

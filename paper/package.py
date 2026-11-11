#!/usr/bin/env python3
"""Build the preprint and verify an independently buildable source archive."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

PAPER = Path(__file__).resolve().parent
REPO = PAPER.parent
DIST = PAPER / "dist"


def build(directory):
    subprocess.run(
        ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
         "-outdir=dist", "main.tex"], cwd=directory, check=True,
    )


def main():
    build(PAPER)
    archive = DIST / "eggfuse-arxiv-source.tar.gz"
    with tempfile.TemporaryDirectory(prefix="eggfuse-paper-") as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        files = sorted(PAPER.glob("*.tex")) + sorted(PAPER.glob("*.dat"))
        files += sorted((PAPER / "figures").glob("*.tex"))
        files += [PAPER / "README.md", PAPER / "submission.txt"]
        for path in files:
            target = source / path.relative_to(PAPER)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        for name in ("eggcc-suite", "upstream-suite"):
            for path in sorted((REPO / "benchmarks" / name).iterdir()):
                if path.suffix not in {".md", ".py", ".rs", ".json", ".jsonl", ".csv"}:
                    continue
                target = source / "anc" / "benchmarks" / name / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        for name in ("transfer_suite.rs", "upstream_suite.rs"):
            path = REPO / "tools" / "cell-compiler" / "examples" / name
            target = source / "anc" / path.relative_to(REPO)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (source / "anc" / "README.txt").write_text(
            "Current benchmark sources and text results, from ce01d785.\n"
            "Measured implementation: 8450e627.\n"
            "These drivers require the full repository and its validator tools.\n"
            "Historical evidence is linked separately in the manuscript.\n"
            "Large exports and executable binaries are not included.\n"
        )
        entries = sorted(path for path in source.rglob("*") if path.is_file())
        (source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(source)}\n"
            for path in entries
        ))
        with tarfile.open(archive, "w:gz") as output:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    output.add(path, arcname=str(path.relative_to(source)))
        verification = Path(temporary) / "verify"
        verification.mkdir()
        with tarfile.open(archive) as packaged:
            packaged.extractall(verification, filter="data")
        build(verification)
    shutil.copyfile(DIST / "main.pdf", DIST / "eggfuse.pdf")
    print(f"Verified source archive: {archive}")
    print(f"PDF: {DIST / 'eggfuse.pdf'}")


if __name__ == "__main__":
    main()

"""
probe_all.py
Run all automated P0 probes and print a summary.
Manual probes (P0-5 Kiro hook, P0-6 extension manifests) are
printed as instructions — fill them in docs/probe-results.md.

Usage:
    venv\\Scripts\\python.exe scripts\\probe_all.py
"""
import sys
import importlib
import textwrap
from pathlib import Path


def _run_module(name: str) -> tuple[str, bool]:
    mod = importlib.import_module(name)
    ok: bool = mod.run()
    return name, ok


PROBES = [
    ("probe_sqlite_pragmas", "P0-1 SQLite PRAGMA compliance"),
    ("probe_sync_root",      "P0-2 Sync-root check"),
    ("probe_file_replace",   "P0-3 os.replace atomic"),
]

MANUAL = textwrap.dedent("""
P0-4  Python / venv
      Run: venv\\Scripts\\python.exe --version
      Confirm packages: fastapi uvicorn pydantic ruff pytest
      Run: venv\\Scripts\\pip.exe list

P0-5  Kiro hook behavior (manual)
      - Create a PostFileSave hook on a test file
      - Note the cwd, exit-code handling, and whether it fires once or twice
      - Record in docs/probe-results.md

P0-6  VS Code extension manifests (manual)
      - Look in %USERPROFILE%\\.vscode\\extensions\\ for claude and codex folders
      - Open each package.json and check contributes.commands
      - Record found command IDs in docs/probe-results.md
""").strip()


def main() -> int:
    # Add scripts/ to path so relative imports work
    sys.path.insert(0, str(Path(__file__).parent))

    results: list[tuple[str, str, bool]] = []

    for module, label in PROBES:
        print(f"\n{'='*50}")
        print(f"{label}")
        print('='*50)
        _, ok = _run_module(module)
        results.append((module, label, ok))

    print(f"\n{'='*50}")
    print("SUMMARY")
    print('='*50)
    all_pass = True
    for _, label, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {label}")
        if not ok:
            all_pass = False

    print(f"\n{'='*50}")
    print("MANUAL PROBES REQUIRED")
    print('='*50)
    print(MANUAL)

    print(f"\n{'='*50}")
    overall = "ALL AUTOMATED PROBES PASSED" if all_pass else "ONE OR MORE PROBES FAILED"
    print(f"Overall: {overall}")
    print("Paste output into docs/probe-results.md before starting Phase 1.")
    print('='*50)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

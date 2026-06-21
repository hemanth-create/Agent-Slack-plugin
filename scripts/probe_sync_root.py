"""
probe_sync_root.py
Check whether the repo lives under a known sync-folder root
(OneDrive, Dropbox, Google Drive, iCloud).
Exit 0 = not synced (safe), exit 1 = synced (hazard).
"""
import os
import sys
from pathlib import Path


SYNC_MARKERS = [
    "OneDrive",
    "Dropbox",
    "Google Drive",
    "GoogleDrive",
    "iCloudDrive",
    "iCloud~com~apple~CloudDocs",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _is_under_sync_root(path: Path) -> tuple[bool, str]:
    parts = path.parts
    for marker in SYNC_MARKERS:
        for part in parts:
            if marker.lower() in part.lower():
                return True, part
    return False, ""


def run() -> bool:
    repo = _repo_root()
    print(f"  Repo path : {repo}")

    synced, marker = _is_under_sync_root(repo)
    if synced:
        print(f"  FAIL — repo is under a sync folder: '{marker}'")
        print("  SQLite WAL+FULL is unreliable on synced paths.")
        print("  Fix: move the repo to a local non-synced folder.")
        return False

    localappdata = os.environ.get("LOCALAPPDATA", "")
    print(f"  LOCALAPPDATA : {localappdata or '(not set)'}")
    if localappdata:
        la_synced, la_marker = _is_under_sync_root(Path(localappdata))
        if la_synced:
            print(f"  WARN — LOCALAPPDATA is under '{la_marker}' — pick a different data dir")
        else:
            print("  LOCALAPPDATA is not synced — safe for data/router.db")

    print("  PASS — repo path is not under a known sync root")
    return True


if __name__ == "__main__":
    print("=== P0-2: Sync-root check ===")
    ok = run()
    print(f"\nResult: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)

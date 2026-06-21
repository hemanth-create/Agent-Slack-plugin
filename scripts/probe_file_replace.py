"""
probe_file_replace.py
Test two things on Windows:
  1. os.replace() FAILS when target has an open read handle (expected on Windows).
  2. os.replace() PASSES when target has no open handle (the pattern we will use).

Exit 0 = mitigation confirmed (case 2 works), exit 1 = even the mitigation fails.
"""
import os
import sys
import tempfile
from pathlib import Path


def _test_replace_while_open(tmpdir: Path) -> bool:
    """Returns True if replace-while-open works (not expected on Windows)."""
    target = tmpdir / "target_open.txt"
    tmp    = tmpdir / "target_open.tmp"
    target.write_text("original", encoding="utf-8")
    try:
        with target.open("r", encoding="utf-8"):
            tmp.write_text("replacement", encoding="utf-8")
            os.replace(str(tmp), str(target))
        return target.read_text(encoding="utf-8") == "replacement"
    except (PermissionError, OSError):
        return False


def _test_replace_after_close(tmpdir: Path) -> bool:
    """Returns True if replace works after all handles are closed (our pattern)."""
    target = tmpdir / "target_closed.txt"
    tmp    = tmpdir / "target_closed.tmp"
    target.write_text("original", encoding="utf-8")
    try:
        # Read content (simulates projection consumer) then close handle
        _ = target.read_text(encoding="utf-8")
        # Now write replacement and replace — no open handle
        tmp.write_text("replacement", encoding="utf-8")
        os.replace(str(tmp), str(target))
        return target.read_text(encoding="utf-8") == "replacement"
    except (PermissionError, OSError) as exc:
        print(f"  FAIL — even close-before-replace failed: {exc}")
        return False


def run() -> bool:
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)

        open_ok = _test_replace_while_open(td)
        print(f"  replace-while-open  : {'OK (unexpected)' if open_ok else 'FAILS (expected on Windows)'}")

        close_ok = _test_replace_after_close(td)
        print(f"  close-before-replace: {'PASS — mitigation works' if close_ok else 'FAIL — mitigation broken'}")

        if close_ok:
            print("\n  Implementation rule: never hold a read handle on a projection")
            print("  file when the writer calls os.replace(). Backend controls all")
            print("  projection reads/writes, so this is enforced in the write path.")

        return close_ok


if __name__ == "__main__":
    print("=== P0-3: os.replace behavior on Windows ===")
    ok = run()
    print(f"\nResult: {'PASS — use close-before-replace' if ok else 'FAIL — escalate'}")
    sys.exit(0 if ok else 1)

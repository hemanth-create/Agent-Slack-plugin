from __future__ import annotations

import json
from pathlib import Path

import wake_driver.local_config as lc


def test_env_var_wins_over_file(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "local_config.json"
    cfg.write_text(json.dumps({"python_bin": "from_file"}), encoding="utf-8")
    monkeypatch.setattr(lc, "_LOCAL_CONFIG", cfg)
    monkeypatch.setenv("WAKE_PYTHON_BIN", "from_env")
    assert lc.python_bin() == "from_env"


def test_local_config_used_when_env_absent(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "local_config.json"
    cfg.write_text(json.dumps({"python_bin": "cfg_py", "secrets_path": "cfg/secrets.json"}),
                   encoding="utf-8")
    monkeypatch.setattr(lc, "_LOCAL_CONFIG", cfg)
    monkeypatch.delenv("WAKE_PYTHON_BIN", raising=False)
    monkeypatch.delenv("WAKE_SECRETS_PATH", raising=False)
    assert lc.python_bin() == "cfg_py"
    assert lc.secrets_path() == Path("cfg/secrets.json")


def test_falls_back_to_defaults_when_nothing_set(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(lc, "_LOCAL_CONFIG", tmp_path / "missing.json")
    monkeypatch.delenv("WAKE_PYTHON_BIN", raising=False)
    monkeypatch.delenv("WAKE_SECRETS_PATH", raising=False)
    assert lc.python_bin()  # sys.executable, always non-empty
    assert lc.secrets_path().name == "secrets.json"


def test_malformed_local_config_is_ignored(monkeypatch, tmp_path) -> None:
    bad = tmp_path / "local_config.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(lc, "_LOCAL_CONFIG", bad)
    monkeypatch.delenv("WAKE_SECRETS_PATH", raising=False)
    assert lc.secrets_path().name == "secrets.json"  # default, no crash

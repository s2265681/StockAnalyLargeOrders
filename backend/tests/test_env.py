import os
import tempfile
from pathlib import Path

from utils import env as env_module


def test_load_env_does_not_override_existing(monkeypatch, tmp_path):
    env_module._loaded = False
    env_file = tmp_path / ".env"
    env_file.write_text("MYSQL_HOST=from_file\nMYSQL_PORT=13306\n", encoding="utf-8")
    monkeypatch.setenv("MYSQL_HOST", "already_set")

    env_module.load_env(env_file=env_file, override=False)

    assert os.environ["MYSQL_HOST"] == "already_set"
    assert os.environ["MYSQL_PORT"] == "13306"


def test_load_env_parses_quoted_values(monkeypatch, tmp_path):
    env_module._loaded = False
    env_file = tmp_path / ".env"
    env_file.write_text('MYSQL_PASSWORD="secret"\n', encoding="utf-8")
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)

    env_module.load_env(env_file=env_file, override=True)

    assert os.environ["MYSQL_PASSWORD"] == "secret"

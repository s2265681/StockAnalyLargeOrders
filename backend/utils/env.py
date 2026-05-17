"""
从 backend/.env 加载环境变量（不覆盖已存在的变量）。
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"
_loaded = False


def load_env(env_file=None, override=False):
    """加载 .env 到 os.environ。默认只加载一次，且不覆盖已有变量。"""
    global _loaded
    path = Path(env_file) if env_file else _ENV_FILE
    if _loaded and env_file is None:
        return path.exists()

    if not path.is_file():
        if env_file is None:
            _loaded = True
        return False

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if not override and key in os.environ:
                continue
            os.environ[key] = value

    if env_file is None:
        _loaded = True

    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = os.environ.get("MYSQL_PORT", "3306")
    database = os.environ.get("MYSQL_DATABASE", "stock")
    logger.info("MySQL 配置: %s:%s/%s (from %s)", host, port, database, path)
    return True

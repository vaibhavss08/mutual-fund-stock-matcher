"""Shared data locations used by both apps."""

import os


APP_DIR = os.path.dirname(__file__)
WORKSPACE_ROOT = os.path.abspath(os.path.join(APP_DIR, ".."))


def _resolve_env_path(env_name, default_path):
    configured = os.environ.get(env_name)
    if not configured:
        return default_path
    return os.path.abspath(configured)


SHARED_DATA_DIR = _resolve_env_path(
    "MF_SHARED_DATA_DIR",
    os.path.join(WORKSPACE_ROOT, "shared-data"),
)
DB_PATH = _resolve_env_path("MF_MATCHER_DB_PATH", os.path.join(SHARED_DATA_DIR, "mf_matcher.db"))
REAL_DATA_PATH = _resolve_env_path("MF_REAL_DATA_PATH", os.path.join(SHARED_DATA_DIR, "real_data.json"))
REAL_HOLDINGS_PATH = _resolve_env_path(
    "MF_REAL_HOLDINGS_PATH",
    os.path.join(SHARED_DATA_DIR, "real_holdings.json"),
)


def ensure_shared_data_dir():
    os.makedirs(SHARED_DATA_DIR, exist_ok=True)
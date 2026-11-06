"""Đọc cấu hình từ file .env và configs/*.yaml."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
RAW_DATA_DIR = ROOT_DIR / os.getenv("RAW_DATA_DIR", "data/raw")
ARTIFACTS_DIR = ROOT_DIR / "artifacts"


def load_yaml(name: str) -> dict:
    with open(ROOT_DIR / "configs" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)

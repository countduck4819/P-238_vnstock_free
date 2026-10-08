import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(
    os.environ.get("FIREANT_DATA_DIR", PROJECT_ROOT / "data")
).expanduser().resolve()


def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)

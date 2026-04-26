import json
from pathlib import Path

_DATA_DIR = Path(__file__).parent


def load(filename: str) -> dict | list:
    with (_DATA_DIR / filename).open() as f:
        return json.load(f)

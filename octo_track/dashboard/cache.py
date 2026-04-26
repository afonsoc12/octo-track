"""Volume-backed parquet cache for stateless mode.

Persists fetched data across container restarts via a mounted Docker volume.
`@st.cache_data` (in-process) sits on top to avoid re-reading parquet on every render.
Cache is permanent — cleared only via the Refresh button in the dashboard.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(os.getenv("CACHE_DIR", "./data/cache"))


def load_or_fetch(key: str, fetch_fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """Return cached DataFrame if it exists, else call fetch_fn, persist, and return."""
    path = CACHE_DIR / f"{key}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    df = fetch_fn()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def invalidate(key: str) -> bool:
    """Delete a cached file. Returns True if it existed."""
    path = CACHE_DIR / f"{key}.parquet"
    if path.exists():
        path.unlink()
        return True
    return False


def cache_key(*parts: str) -> str:
    """Build a safe filename key from parts."""
    return "_".join(str(p).replace("/", "-").replace(":", "-").replace("+", "") for p in parts)

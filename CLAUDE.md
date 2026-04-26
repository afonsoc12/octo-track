# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OctoTrack** is a Streamlit dashboard that fetches electricity consumption and tariff data live from the Octopus Energy API. Stateless — no database required. Runs as a Docker container.

Key constraints:
- Consumption data from Octopus API has a ~1 day delay.
- Requires Python ≥ 3.14 and `uv` as the package manager.
- All account/meter/tariff info is auto-discovered from `OCTOPUS_API_KEY`.

## Commands

```bash
# Install dependencies
uv sync --locked --all-groups

# Run the dashboard (with env vars from .env)
uv run --env-file .env octo-track dashboard

# Linting and formatting
uv run ruff format octo_track test        # auto-fix
uv run ruff format --check octo_track test  # CI check
uv run ruff check --fix octo_track test

# Tests
uv run pytest -m "not integration" -v
```

## Architecture

```
octo_track/
  __main__.py           # CLI entry point (Click) — only `dashboard` command
  octopus.py            # Octopus API client (subclasses requests.Session)
  logging_config.py     # Structured logging (text or logfmt)
  models/
    consumption.py      # ElectricityConsumption dataclass
  dashboard/
    app.py              # Streamlit page navigation
    data.py             # API fetchers + caching (stateless only)
    cache.py            # Volume-backed parquet cache (permanent, no TTL)
    shared.py           # Shared UI components
    pages/
      daily_overview.py
      halfhourly.py
      agile_rates.py
```

### Data flow

1. Dashboard auto-discovers account/meter/tariff via `fetch_account_data()` (GraphQL + REST).
2. Consumption and rates fetched from Octopus API, cached to parquet on disk.
3. Cache is permanent — cleared only via the ↺ Refresh button.
4. `build_rate_index` + `bisect_right` used for O(log n) rate lookups per interval.

### Octopus API client

`Octopus` extends `requests.Session`. All requests go through `_request()` which builds URLs as `BASE_URL + API_ENDPOINT + endpoint`. Key endpoints:
- `v1/electricity-meter-points/{mpan}/meters/{sn}/consumption`
- `v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/`
- `v1/accounts/{account_number}/`
- GraphQL: `obtainKrakenToken` + `viewer { accounts { number } }`

## Environment Variables

| Variable | Purpose |
|---|---|
| `OCTOPUS_API_KEY` | API auth (used as HTTP Basic username) — only required var |
| `CACHE_DIR` | Parquet cache directory (default `./data/cache`, Docker: `/data/cache`) |
| `LOG_LEVEL` | Logging verbosity (default `INFO`) |
| `LOG_FORMAT` | `text` or `logfmt` (default `text`) |

## Testing

Tests live in `test/`. Fixtures and sample API responses are in `test/data/`.

Pre-commit runs ruff format, ruff lint, and unit tests on every commit.

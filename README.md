# 🐙 OctoTrack

> ⚡ Electricity usage dashboard for [Octopus Energy](https://octopus.energy/) customers — no database required.

**OctoTrack** is a Streamlit dashboard that fetches your electricity consumption and tariff data live from the Octopus Energy API. Just drop in your API key and go.

## ✨ Features

- 📊 **Monthly overview** — consumption and cost breakdown by month, with Ofgem price cap reference lines
- ⏱️ **Half-hourly detail** — 30-minute interval analysis for any date range
- ⚡ **Agile rates** — live Agile tariff rate visualisation and cost comparison against your current tariff
- 🔍 **Auto-discovery** — meter points and tariff history resolved automatically from your account (no MPAN/meter SN needed)
- 💾 **Smart caching** — API responses cached to disk (parquet) to avoid hammering the API; configurable TTL
- 🐳 **Single container** — one Docker image, one env var to get started

> 📌 Octopus consumption data is available with a ~1 day delay. Yesterday's data appears sometime this morning.

## 🚀 Quick Start

### Docker (recommended)

```bash
docker run -e OCTOPUS_API_KEY=sk_live_... -p 8501:8501 ghcr.io/afonsoc12/octo-track
```

Then open [http://localhost:8501](http://localhost:8501).

### Docker Compose

```bash
# .env
OCTOPUS_API_KEY=sk_live_...

docker compose up
```

### Local (Python ≥ 3.14 + uv)

```bash
uv sync --locked --all-groups
uv run --env-file .env python -m octo_track dashboard
```

## ⚙️ Configuration

All configuration is via environment variables. Only `OCTOPUS_API_KEY` is required — everything else is auto-discovered or has a sensible default.

### 🔑 Required

| Variable | Description | Example |
|---|---|---|
| `OCTOPUS_API_KEY` | Octopus Energy API key | `sk_live_...` |

Get your API key from [Octopus Energy → Personal details → API access](https://octopus.energy/dashboard/new/accounts/personal-details/api-access).

All meter points, tariffs, and account info are auto-discovered from the API key. No other credentials needed.

### 💾 Cache

| Variable | Description | Default |
|---|---|---|
| `CACHE_DIR` | Directory for parquet cache files | `/data/cache` |

Cache is permanent — cleared only when you hit **↺ Refresh** in the dashboard.

### 🎛️ Streamlit

Any `STREAMLIT_*` environment variable is passed through to Streamlit and takes effect at runtime. Use this to configure the server port, address, theme, and more.

```bash
# Examples
STREAMLIT_SERVER_PORT=8080
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_THEME_BASE=dark
```

See the full list of options at [Streamlit configuration options](https://docs.streamlit.io/develop/concepts/configuration/options) and [config.toml reference](https://docs.streamlit.io/develop/api-reference/configuration/config.toml).

### 🪵 Logging

| Variable | Description | Default | Example |
|---|---|---|---|
| `LOG_LEVEL` | Logging verbosity | `INFO` | `DEBUG` |
| `LOG_FORMAT` | Log format (`text` or `logfmt`) | `text` | `logfmt` |
| `DASHBOARD_PORT` | Host port mapping (Docker only) | `8501` | `8080` |

### 📝 Example `.env`

```bash
OCTOPUS_API_KEY=sk_live_your_key_here
```

## 🐳 Docker Details

The image uses a multi-stage build (Python 3.14-slim). It runs as a non-root user (`octo`, UID 1000).

```
ENTRYPOINT ["octo-track"]
CMD ["dashboard", "--stateless"]
```

Override the port:

```bash
docker run -e OCTOPUS_API_KEY=sk_live_... -p 8080:8501 ghcr.io/afonsoc12/octo-track
```

Mount a persistent cache volume to survive container restarts:

```bash
docker run \
  -e OCTOPUS_API_KEY=sk_live_... \
  -v octo-cache:/data/cache \
  -p 8501:8501 \
  ghcr.io/afonsoc12/octo-track
```

## 🗺️ Roadmap

- [ ] Server mode — background job that fetches data automatically (asyncio/scheduler)
- [ ] More sidebar account info — postcode, town, current tariff, move-in date
- [ ] Integration tests
- [ ] Combine GraphQL + REST APIs into unified client

## 📄 License

**Copyright © 2026 [Afonso Costa](https://github.com/afonsoc12)**

Licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.

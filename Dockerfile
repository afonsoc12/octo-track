# ── builder ──────────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app
COPY . .
RUN uv sync --locked --no-editable --no-dev --all-groups

# ── runtime ───────────────────────────────────────────────────────────────────
FROM docker.io/library/python:3.14-slim-trixie

ARG USER=octo \
    UID=1000 \
    GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    CACHE_DIR=/data/cache \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN groupadd --gid $GID $USER \
    && useradd --create-home --uid $UID --gid $GID $USER \
    && mkdir -p /data \
    && chown -R $UID:$GID /app /data

COPY --from=builder --chown=$USER:$USER /app/.venv ./.venv

USER $USER
VOLUME /data
EXPOSE 8501

ENTRYPOINT ["octo-track"]
CMD ["dashboard", "--stateless"]

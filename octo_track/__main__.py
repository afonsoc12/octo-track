#!/usr/bin/env python3
"""CLI for octo-track.

Execute with:
  $ octo-track dashboard
  $ octo-track dashboard --stateless
"""

import os
import subprocess
import sys

import click

from octo_track.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


@click.group()
def cli():
    """Octopus Energy usage dashboard."""


@cli.command()
@click.option("--api-key", envvar="OCTOPUS_API_KEY", help="Octopus Energy API key")
@click.option("--stateless", is_flag=True, default=True, help="Fetch data from Octopus API at runtime (default)")
def dashboard(api_key, stateless):
    """Launch the Streamlit dashboard (fetches live from Octopus Energy API)."""
    setup_logging()

    env = os.environ.copy()
    if api_key:
        env["OCTOPUS_API_KEY"] = api_key

    env["OCTO_MODE"] = "stateless"
    logger.info("Dashboard mode: stateless")

    app_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "dashboard", "app.py"))
    cmd = [sys.executable, "-m", "streamlit", "run", app_path]
    try:
        subprocess.run(cmd, env=env, check=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()

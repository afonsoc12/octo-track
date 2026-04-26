# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog],
and this project adheres to [Semantic Versioning].

## [Unreleased]

## [0.0.1] - 2026-04-26

### Added

- 📊 Monthly overview — daily consumption and cost breakdown with Ofgem SVT price cap comparison
- ⏱️ Half-hourly detail — 30-minute interval analysis with rate and cost per slot
- ⚡ Agile rates — live Agile tariff visualisation, rate bands, and cost comparison vs current tariff
- 🔍 Auto-discovery — account, meter points, and tariff history resolved from API key alone
- 💾 Parquet cache — API responses cached to disk, cleared via Refresh button
- 🐳 Docker image — multi-stage build, non-root user, single env var to run

<!-- Links -->

[Keep a Changelog]: https://keepachangelog.com/en/1.0.0/
[Semantic Versioning]: https://semver.org/spec/v2.0.0.html

<!-- Versions -->

[unreleased]: https://github.com/afonsoc12/octo-track/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/afonsoc12/octo-track/releases/tag/v0.0.1

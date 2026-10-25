# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-25

### Added

- fsmon CLI: latest file system usage per host and mount from Metricbeat data, thresholds, table/JSON/Nagios output and Nagios-compatible exit codes
- Elasticsearch client with API key or basic authentication and clear error reporting
- Docker Compose lab: Elasticsearch, Kibana and Metricbeat with security enabled and host dashboards
- ILM policy and Kibana alert rule for file system capacity, with a loader script
- CI pipeline: lint, strict typing, unit tests on Python 3.10-3.13, live Elasticsearch integration test, lab validation and security scanning

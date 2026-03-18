# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

xmrig_exporter is a Prometheus exporter for XMRig cryptocurrency miners and xmrig-proxy. It polls the XMRig HTTP API and exposes mining metrics in Prometheus format. The exporter supports both individual miners (XMRig) and proxy servers (xmrig-proxy) with automatic detection.

## Architecture

The codebase supports both single-target and multi-target monitoring:

- **exporter.py**: Entry point that handles CLI arguments (--url or --config), selects appropriate collector, and starts the HTTP server on port 9189 (default)
- **collector.py**: `XmrigCollector` for single miner monitoring, plus `extract_miner_metrics()` function and `add_metric_to_families()` helper
- **proxy_collector.py**: `XmrigProxyCollector` for single proxy monitoring, plus `extract_proxy_metrics()` function
- **multi_collector.py**: `MultiCollector` for monitoring multiple targets with `xmrig_target` labels

### Single-Target Mode (--url)
Uses original `XmrigCollector` or `XmrigProxyCollector`. Auto-detection logic: If the API response contains both "miners" and "workers" fields, it's a proxy; otherwise it's a miner. **No xmrig_target label is added** (backward compatible).

### Multi-Target Mode (--config)
Uses `MultiCollector` which aggregates metrics from multiple targets using a shared `dict[str, MetricFamily]` pattern. Each target gets an **xmrig_target label** to distinguish instances. Supports mixed miner/proxy targets with auto-detection per target.

## Development Commands

Install in development mode:
```bash
pip install -e .
```

Run the exporter:
```bash
# For XMRig miner
xmrig_exporter --url http://localhost:8080/1/summary --mode miner

# For xmrig-proxy
xmrig_exporter --url http://localhost:8080/1/summary --mode proxy

# Auto-detect mode (default)
xmrig_exporter --url http://localhost:8080/1/summary

# With authentication token
xmrig_exporter --url http://localhost:8080/1/summary --token YOUR_TOKEN

# With verbose logging
xmrig_exporter --url http://localhost:8080/1/summary -v

# Multi-target mode with YAML config
xmrig_exporter --config config.yaml
```

### Multi-Target Configuration

Create a YAML config file to monitor multiple xmrig/xmrig-proxy instances:

```yaml
targets:
  - name: rig-01
    url: http://192.168.1.10:8080/1/summary
    mode: auto  # or 'miner' or 'proxy'
    token: optional-bearer-token  # optional
    timeout: 5  # optional, in seconds

  - name: rig-02
    url: http://192.168.1.11:8080/1/summary
    mode: miner

  - name: proxy-01
    url: http://192.168.1.20:8080/1/summary
    mode: proxy
    token: secret-token
    timeout: 10
```

Then run:
```bash
xmrig_exporter --config config.yaml
```

Build Docker image:
```bash
docker build -t xmrig_exporter .
```

Run in Docker (single-target):
```bash
docker run -p 9189:9189 xmrig_exporter --url http://host.docker.internal:8080/1/summary
```

Run in Docker (multi-target with config file):
```bash
docker run -p 9189:9189 -v /path/to/config.yaml:/config.yaml:ro xmrig_exporter --config /config.yaml
```

## Issue Tracking

This project uses the beads issue tracker (agent-first SQLite + JSONL tracker). Access it using the `br` command:

```bash
# List all issues
br list

# Create a new issue
br create "Issue title"

# View issue details
br show <issue-id>

# Close an issue
br close <issue-id>

# List blocked issues
br blocked

# View other commands
br --help
```

The beads database is stored in `.beads/` directory.

## Key Implementation Details

### Collector Pattern
Both collectors inherit from a Prometheus collector interface and implement `collect()`. They use `make_metric()` helper to create CounterMetricFamily (for cumulative values like shares_total) or GaugeMetricFamily (for current values like hashrate).

### Metric Naming
- XmrigCollector uses prefix `xmrig_`
- XmrigProxyCollector uses prefix `xmrig_proxy_`
- All metrics are labeled with `worker_id` from the API response
- **Multi-target mode**: All metrics also get an `xmrig_target` label (not present in single-target mode)

### Health Monitoring
In multi-target mode, the exporter emits `xmrig_up` or `xmrig_proxy_up` gauges:
- Value `1` = target is reachable
- Value `0` = target is unreachable

These gauges have `xmrig_target` labels to identify which target failed.

### Authentication
Both collectors support Bearer token authentication via the `--token` CLI argument, which is passed in the Authorization header.

### Backward Compatibility
The package exports `exporter_main` as an alias for `main()` (see __init__.py:8) to maintain compatibility with older installations.

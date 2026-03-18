import argparse
import http.server
import logging
import sys
import yaml

import prometheus_client

import xmrig_exporter


def load_config(config_path):
    """
    Load YAML config file and validate it.

    Expected format:
    targets:
      - name: rig-01
        url: http://192.168.1.10:8080/1/summary
        token: optional-bearer-token
        mode: auto  # or 'miner' or 'proxy'
        timeout: 5  # optional, in seconds

    Returns:
        list of target dicts
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise ValueError(f"Config file not found: {config_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file: {e}")

    if not isinstance(config, dict):
        raise ValueError("Config file must contain a YAML dictionary")

    if 'targets' not in config:
        raise ValueError("Config file must have 'targets' key")

    targets = config['targets']
    if not isinstance(targets, list):
        raise ValueError("'targets' must be a list")

    if len(targets) == 0:
        raise ValueError("'targets' list cannot be empty")

    # Validate each target
    for i, target in enumerate(targets):
        if not isinstance(target, dict):
            raise ValueError(f"Target {i} must be a dictionary")

        if 'url' not in target:
            raise ValueError(f"Target {i} missing required 'url' field")

        if 'name' not in target:
            raise ValueError(f"Target {i} missing required 'name' field")

        # Set defaults
        target.setdefault('mode', 'auto')
        target.setdefault('token', None)
        target.setdefault('timeout', 5)

        # Validate mode
        if target['mode'] not in ['miner', 'proxy', 'auto']:
            raise ValueError(f"Target {i} has invalid mode: {target['mode']} (must be 'miner', 'proxy', or 'auto')")

    return targets


def main():
    parser = argparse.ArgumentParser("Xmrig Exporter")

    parser.add_argument("--port", type=int, default=9189)
    parser.add_argument("--bind_address", default="0.0.0.0")

    # Create mutually exclusive group for --url and --config
    config_group = parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument("--url", help="Single target URL (for backward compatibility)")
    config_group.add_argument("--config", help="Path to YAML config file with multiple targets")

    parser.add_argument("--token")
    parser.add_argument("--mode", choices=["miner", "proxy", "auto"], default="auto",
                        help="Exporter mode: miner for XMRig, proxy for xmrig-proxy, auto to detect (only used with --url)")
    parser.add_argument("--verbose", "-v", action="count")

    args = parser.parse_args()

    if args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(stream=sys.stdout, level=level)

    # Single-target mode (--url): use original collectors for backward compatibility
    if args.url:
        logging.info("Single-target mode (--url): using original collectors")

        # Select collector based on mode
        if args.mode == "proxy":
            collector = xmrig_exporter.XmrigProxyCollector(args.url, token=args.token)
            logging.info("Using XmrigProxyCollector (proxy mode)")
        elif args.mode == "miner":
            collector = xmrig_exporter.XmrigCollector(args.url, token=args.token)
            logging.info("Using XmrigCollector (miner mode)")
        else:
            # Auto-detect mode by checking API response
            import requests
            headers = {}
            if args.token:
                headers["Authorization"] = "Bearer " + args.token
            try:
                j = requests.get(args.url, headers=headers, timeout=5).json()
                # xmrig-proxy has "miners" and "workers" fields, xmrig has "threads"
                if "miners" in j and "workers" in j:
                    collector = xmrig_exporter.XmrigProxyCollector(args.url, token=args.token)
                    logging.info("Auto-detected: Using XmrigProxyCollector (proxy mode)")
                else:
                    collector = xmrig_exporter.XmrigCollector(args.url, token=args.token)
                    logging.info("Auto-detected: Using XmrigCollector (miner mode)")
            except Exception as e:
                logging.error(f"Failed to auto-detect mode: {e}")
                logging.info("Defaulting to XmrigCollector (miner mode)")
                collector = xmrig_exporter.XmrigCollector(args.url, token=args.token)

    # Multi-target mode (--config): use MultiCollector with xmrig_target labels
    else:
        logging.info(f"Multi-target mode (--config): loading {args.config}")
        try:
            targets = load_config(args.config)
            logging.info(f"Loaded {len(targets)} targets from config")
            for target in targets:
                logging.info(f"  - {target['name']}: {target['url']} (mode: {target['mode']})")

            collector = xmrig_exporter.MultiCollector(targets)
            logging.info("Using MultiCollector for multi-target monitoring")
        except ValueError as e:
            logging.error(f"Config validation failed: {e}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            sys.exit(1)

    prometheus_client.REGISTRY.register(collector)

    handler = prometheus_client.MetricsHandler.factory(
            prometheus_client.REGISTRY)
    server = http.server.HTTPServer(
            (args.bind_address, args.port), handler)
    logging.info(f"Starting server on {args.bind_address}:{args.port}")
    server.serve_forever()

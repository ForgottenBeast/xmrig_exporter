import argparse
import http.server
import logging
import sys

import prometheus_client

import xmrig_exporter


def main():
    parser = argparse.ArgumentParser("Xmrig Exporter")

    parser.add_argument("--port", type=int, default=9189)
    parser.add_argument("--bind_address", default="0.0.0.0")
    parser.add_argument("--url", required=True)
    parser.add_argument("--token")
    parser.add_argument("--mode", choices=["miner", "proxy", "auto"], default="auto",
                        help="Exporter mode: miner for XMRig, proxy for xmrig-proxy, auto to detect")
    parser.add_argument("--verbose", "-v", action="count")

    args = parser.parse_args()

    if args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(stream=sys.stdout, level=level)

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
            j = requests.get(args.url, headers=headers).json()
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

    prometheus_client.REGISTRY.register(collector)

    handler = prometheus_client.MetricsHandler.factory(
            prometheus_client.REGISTRY)
    server = http.server.HTTPServer(
            (args.bind_address, args.port), handler)
    logging.info(f"Starting server on {args.bind_address}:{args.port}")
    server.serve_forever()

import logging
import requests
import prometheus_client.core
from .collector import extract_miner_metrics
from .proxy_collector import extract_proxy_metrics


class MultiCollector(object):
    """
    Collector that aggregates metrics from multiple xmrig/xmrig-proxy targets.

    Each target is scraped sequentially. Metrics from all targets are merged
    into a single set of MetricFamily objects with an xmrig_target label to
    distinguish instances.
    """

    def __init__(self, targets, timeout=5):
        """
        Initialize MultiCollector.

        Args:
            targets: list of dict with keys:
                - name: str - target identifier for xmrig_target label
                - url: str - API endpoint URL
                - token: str | None - bearer token for authentication
                - mode: str - 'miner', 'proxy', or 'auto'
                - timeout: int | None - per-target timeout (uses default if None)
            timeout: int - default timeout in seconds for HTTP requests
        """
        self.targets = targets
        self.default_timeout = timeout

    def collect(self):
        """
        Collect metrics from all targets and yield unified MetricFamily objects.

        For each target:
        1. Fetch JSON from API (single HTTP call)
        2. Auto-detect mode if needed (using same JSON response)
        3. Extract metrics with xmrig_target label
        4. On error: emit _up=0 and skip to next target

        All metrics are merged into a shared dict to avoid duplicate MetricFamily names.
        """
        # Shared dict for all targets - one MetricFamily per metric name
        families = {}

        for target in self.targets:
            target_name = target['name']
            url = target['url']
            token = target.get('token')
            mode = target.get('mode', 'auto')  # Initialize before try block
            timeout = target.get('timeout', self.default_timeout)

            try:
                # Fetch JSON once per target
                headers = {}
                if token:
                    headers["Authorization"] = "Bearer " + token

                json_data = requests.get(url, headers=headers, timeout=timeout).json()

                # Auto-detect mode from same JSON response
                if mode == 'auto':
                    # xmrig-proxy has 'miners' and 'workers' fields
                    if 'miners' in json_data and 'workers' in json_data:
                        mode = 'proxy'
                    else:
                        mode = 'miner'

                # Extract metrics with xmrig_target label
                extra_labels = {'xmrig_target': target_name}

                if mode == 'proxy':
                    extract_proxy_metrics(json_data, families, extra_labels)
                    up_metric_name = 'xmrig_proxy_up'
                else:
                    extract_miner_metrics(json_data, families, extra_labels)
                    up_metric_name = 'xmrig_up'

                # Add _up=1 gauge for this target
                up_labels = extra_labels.copy()
                if 'worker_id' in json_data:
                    up_labels['worker_id'] = json_data.get('worker_id', 'unknown')

                if up_metric_name not in families:
                    label_names = sorted(up_labels.keys())
                    families[up_metric_name] = prometheus_client.core.GaugeMetricFamily(
                        up_metric_name,
                        "Target reachability (1=up, 0=down)",
                        labels=label_names
                    )

                label_values = [str(up_labels[k]) for k in sorted(up_labels.keys())]
                families[up_metric_name].add_metric(label_values, 1)

            except Exception as e:
                # Log error with target name for debugging
                logging.warning(f"Failed to scrape target {target_name} ({url}): {e}")

                # Emit _up=0 for this target
                # Determine metric name prefix based on mode
                if mode == 'proxy':
                    up_metric_name = 'xmrig_proxy_up'
                else:
                    up_metric_name = 'xmrig_up'

                # Use consistent label schema: include worker_id even on error
                up_labels = {'xmrig_target': target_name, 'worker_id': 'unknown'}

                if up_metric_name not in families:
                    label_names = sorted(up_labels.keys())
                    families[up_metric_name] = prometheus_client.core.GaugeMetricFamily(
                        up_metric_name,
                        "Target reachability (1=up, 0=down)",
                        labels=label_names
                    )

                label_values = [str(up_labels[k]) for k in sorted(up_labels.keys())]
                families[up_metric_name].add_metric(label_values, 0)

                # Continue to next target (graceful degradation)
                continue

        # Yield all families once
        for family in families.values():
            yield family

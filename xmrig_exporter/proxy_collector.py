import prometheus_client
import prometheus_client.core
import requests
from .collector import add_metric_to_families


def extract_proxy_metrics(json_data, families, extra_labels=None):
    """
    Extract proxy metrics from xmrig-proxy JSON response and add them to families dict.

    Args:
        json_data: dict - parsed JSON from xmrig-proxy API
        families: dict[str, MetricFamily] - shared dict to mutate
        extra_labels: dict[str, str] | None - additional labels to add (e.g., xmrig_target)
    """
    prefix = "xmrig_proxy_"
    base_labels = {"worker_id": json_data.get("worker_id", "unknown")}

    # Merge extra_labels if provided
    if extra_labels:
        base_labels.update(extra_labels)

    # Miners metrics
    if "miners" in json_data:
        add_metric_to_families(
            families, False, prefix + "miners_now",
            "Number of miners currently connected",
            json_data["miners"]["now"], base_labels
        )
        add_metric_to_families(
            families, False, prefix + "miners_max",
            "Maximum number of miners seen",
            json_data["miners"]["max"], base_labels
        )

    # Workers count
    if "workers" in json_data:
        add_metric_to_families(
            families, False, prefix + "workers",
            "Number of workers",
            json_data["workers"], base_labels
        )

    # Hashrate metrics
    if "hashrate" in json_data and "total" in json_data["hashrate"]:
        for i, v in enumerate(json_data["hashrate"]["total"]):
            if v is not None:
                hashrate_labels = base_labels.copy()
                hashrate_labels["time_index"] = i
                add_metric_to_families(
                    families, False, prefix + "hashrate_total",
                    "Total hashrate across all miners",
                    v, hashrate_labels
                )

    # Upstreams metrics
    if "upstreams" in json_data:
        add_metric_to_families(
            families, False, prefix + "upstreams_active",
            "Number of active upstream connections",
            json_data["upstreams"].get("active", 0), base_labels
        )
        add_metric_to_families(
            families, False, prefix + "upstreams_total",
            "Total number of upstream connections",
            json_data["upstreams"].get("total", 0), base_labels
        )
        if "ratio" in json_data["upstreams"]:
            add_metric_to_families(
                families, False, prefix + "upstreams_ratio",
                "Upstream ratio",
                json_data["upstreams"]["ratio"], base_labels
            )

    # Results metrics
    if "results" in json_data:
        add_metric_to_families(
            families, True, prefix + "results_accepted",
            "Number of accepted shares",
            json_data["results"].get("accepted", 0), base_labels
        )
        add_metric_to_families(
            families, True, prefix + "results_rejected",
            "Number of rejected shares",
            json_data["results"].get("rejected", 0), base_labels
        )
        add_metric_to_families(
            families, True, prefix + "results_invalid",
            "Number of invalid shares",
            json_data["results"].get("invalid", 0), base_labels
        )
        add_metric_to_families(
            families, True, prefix + "results_expired",
            "Number of expired shares",
            json_data["results"].get("expired", 0), base_labels
        )
        if "avg_time" in json_data["results"]:
            add_metric_to_families(
                families, False, prefix + "results_avg_time",
                "Average time between shares",
                json_data["results"]["avg_time"], base_labels
            )
        if "latency" in json_data["results"]:
            add_metric_to_families(
                families, False, prefix + "results_latency",
                "Latency to upstream pool",
                json_data["results"]["latency"], base_labels
            )

    # Uptime
    if "uptime" in json_data:
        add_metric_to_families(
            families, False, prefix + "uptime_seconds",
            "Proxy uptime in seconds",
            json_data["uptime"], base_labels
        )


class XmrigProxyCollector(object):
    """Collector for xmrig-proxy metrics"""

    def __init__(self, url, token=None):
        self.url = url
        self.token = token
        self._prefix = "xmrig_proxy_"

    def make_metric(self, is_counter, _name, _documentation, _value, **_labels):
        label_names = list(_labels.keys())
        if is_counter:
            cls = prometheus_client.core.CounterMetricFamily
        else:
            cls = prometheus_client.core.GaugeMetricFamily
        metric = cls(
            _name, _documentation or "No Documentation", labels=label_names)
        metric.add_metric([str(_labels[k]) for k in label_names], _value)
        return metric

    def collect(self):
        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        j = requests.get(self.url, headers=headers).json()

        # Use extracted function with no extra labels (backward compatible)
        families = {}
        extract_proxy_metrics(j, families, extra_labels=None)

        # Yield all families
        for family in families.values():
            yield family

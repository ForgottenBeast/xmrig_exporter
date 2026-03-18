import prometheus_client
import prometheus_client.core
import requests


def add_metric_to_families(families, is_counter, name, documentation, value, labels):
    """
    Add a metric sample to the families dict.

    If the metric family doesn't exist, create it.
    If it exists, append the sample to the existing family.

    Args:
        families: dict[str, MetricFamily] - shared dict of metric families
        is_counter: bool - whether this is a counter (vs gauge)
        name: str - metric name
        documentation: str - metric documentation
        value: float - metric value
        labels: dict[str, str] - labels for this sample (must be consistent for same metric name)
    """
    if name not in families:
        # Create new family with sorted label names for consistency
        label_names = sorted(labels.keys())
        if is_counter:
            cls = prometheus_client.core.CounterMetricFamily
        else:
            cls = prometheus_client.core.GaugeMetricFamily
        families[name] = cls(name, documentation or "No Documentation", labels=label_names)

    # Add sample to existing family (label values must match the label_names order)
    family = families[name]
    label_values = [str(labels[k]) for k in sorted(labels.keys())]
    family.add_metric(label_values, value)


def extract_miner_metrics(json_data, families, extra_labels=None):
    """
    Extract miner metrics from XMRig JSON response and add them to families dict.

    Args:
        json_data: dict - parsed JSON from XMRig API
        families: dict[str, MetricFamily] - shared dict to mutate
        extra_labels: dict[str, str] | None - additional labels to add (e.g., xmrig_target)
    """
    prefix = "xmrig_"
    base_labels = {"worker_id": json_data["worker_id"]}

    # Merge extra_labels if provided
    if extra_labels:
        base_labels.update(extra_labels)

    # Hashrate metrics (total)
    for i, v in enumerate(json_data["hashrate"]["total"]):
        if v is not None:
            add_metric_to_families(
                families,
                False,
                prefix + "hashrate%d" % i,
                "Overall Hashrate",
                v,
                base_labels
            )

    # Thread hashrate metrics
    for tidx, t in enumerate(json_data["hashrate"]["threads"]):
        for i, v in enumerate(t):
            if v is not None:
                thread_labels = base_labels.copy()
                thread_labels["thread"] = tidx
                add_metric_to_families(
                    families,
                    False,
                    prefix + "thread_hashrate%d" % i,
                    "Thread Hashrate",
                    v,
                    thread_labels
                )

    # Results metrics
    add_metric_to_families(
        families, False, prefix + "diff_current", "Current Difficulty",
        json_data["results"]["diff_current"], base_labels
    )
    add_metric_to_families(
        families, True, prefix + "shares_good", "Good Shares",
        json_data["results"]["shares_good"], base_labels
    )
    add_metric_to_families(
        families, True, prefix + "shares_total", "Total Shares",
        json_data["results"]["shares_total"], base_labels
    )
    add_metric_to_families(
        families, False, prefix + "avg_time", "Average Time",
        json_data["results"]["avg_time"], base_labels
    )
    add_metric_to_families(
        families, True, prefix + "hashes_total", "Total Hashes",
        json_data["results"]["hashes_total"], base_labels
    )
    add_metric_to_families(
        families, False, prefix + "best", "Best",
        json_data["results"]["best"][0], base_labels
    )
    add_metric_to_families(
        families, True, prefix + "errors", "Count of errors",
        len(json_data["results"]["error_log"]), base_labels
    )

    # Connection metrics
    add_metric_to_families(
        families, False, prefix + "connection_uptime", "Connection uptime",
        json_data["connection"]["uptime"], base_labels
    )
    add_metric_to_families(
        families, False, prefix + "connection_ping", "Connection ping",
        json_data["connection"]["ping"], base_labels
    )
    add_metric_to_families(
        families, True, prefix + "connection_failures", "Connection failures",
        json_data["connection"]["failures"], base_labels
    )


class XmrigCollector(object):

    def __init__(self, url, token=None):
        self.url = url
        self.token = token
        self._prefix = "xmrig_"

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
        extract_miner_metrics(j, families, extra_labels=None)

        # Yield all families
        for family in families.values():
            yield family

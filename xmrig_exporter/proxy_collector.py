import prometheus_client
import prometheus_client.core
import requests


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
        metrics = []
        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        j = requests.get(self.url, headers=headers).json()

        # Use worker_id as identifier
        ids = {"worker_id": j.get("worker_id", "unknown")}

        # Miners metrics (PRIMARY METRIC)
        if "miners" in j:
            metrics.append(self.make_metric(
                False,
                self._prefix + "miners_now",
                "Number of miners currently connected",
                j["miners"]["now"],
                **ids))
            metrics.append(self.make_metric(
                False,
                self._prefix + "miners_max",
                "Maximum number of miners seen",
                j["miners"]["max"],
                **ids))

        # Workers count
        if "workers" in j:
            metrics.append(self.make_metric(
                False,
                self._prefix + "workers",
                "Number of workers",
                j["workers"],
                **ids))

        # Hashrate metrics
        if "hashrate" in j and "total" in j["hashrate"]:
            for i, v in enumerate(j["hashrate"]["total"]):
                if v is not None:
                    labels = {"time_index": i}
                    labels.update(ids)
                    metrics.append(self.make_metric(
                        False,
                        self._prefix + "hashrate_total",
                        "Total hashrate across all miners",
                        v,
                        **labels))

        # Upstreams metrics
        if "upstreams" in j:
            metrics.append(self.make_metric(
                False,
                self._prefix + "upstreams_active",
                "Number of active upstream connections",
                j["upstreams"].get("active", 0),
                **ids))
            metrics.append(self.make_metric(
                False,
                self._prefix + "upstreams_total",
                "Total number of upstream connections",
                j["upstreams"].get("total", 0),
                **ids))
            if "ratio" in j["upstreams"]:
                metrics.append(self.make_metric(
                    False,
                    self._prefix + "upstreams_ratio",
                    "Upstream ratio",
                    j["upstreams"]["ratio"],
                    **ids))

        # Results metrics
        if "results" in j:
            metrics.append(self.make_metric(
                True,
                self._prefix + "results_accepted",
                "Number of accepted shares",
                j["results"].get("accepted", 0),
                **ids))
            metrics.append(self.make_metric(
                True,
                self._prefix + "results_rejected",
                "Number of rejected shares",
                j["results"].get("rejected", 0),
                **ids))
            metrics.append(self.make_metric(
                True,
                self._prefix + "results_invalid",
                "Number of invalid shares",
                j["results"].get("invalid", 0),
                **ids))
            metrics.append(self.make_metric(
                True,
                self._prefix + "results_expired",
                "Number of expired shares",
                j["results"].get("expired", 0),
                **ids))
            if "avg_time" in j["results"]:
                metrics.append(self.make_metric(
                    False,
                    self._prefix + "results_avg_time",
                    "Average time between shares",
                    j["results"]["avg_time"],
                    **ids))
            if "latency" in j["results"]:
                metrics.append(self.make_metric(
                    False,
                    self._prefix + "results_latency",
                    "Latency to upstream pool",
                    j["results"]["latency"],
                    **ids))

        # Uptime
        if "uptime" in j:
            metrics.append(self.make_metric(
                False,
                self._prefix + "uptime_seconds",
                "Proxy uptime in seconds",
                j["uptime"],
                **ids))

        return metrics

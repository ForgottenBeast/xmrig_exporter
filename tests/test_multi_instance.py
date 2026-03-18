"""
Comprehensive tests for multi-instance support
"""
import pytest
from unittest.mock import Mock, patch, mock_open
import json

from xmrig_exporter.collector import extract_miner_metrics, add_metric_to_families, XmrigCollector
from xmrig_exporter.proxy_collector import extract_proxy_metrics, XmrigProxyCollector
from xmrig_exporter.multi_collector import MultiCollector
from xmrig_exporter.exporter import load_config


# Sample API responses
MINER_RESPONSE = {
    "worker_id": "test-miner-1",
    "hashrate": {
        "total": [1000.5, 2000.3, None],
        "threads": [[100.1, 200.2], [150.3, None]]
    },
    "results": {
        "diff_current": 50000,
        "shares_good": 100,
        "shares_total": 105,
        "avg_time": 45,
        "hashes_total": 1000000,
        "best": [60000, 12345],
        "error_log": []
    },
    "connection": {
        "uptime": 3600,
        "ping": 50,
        "failures": 2
    }
}

PROXY_RESPONSE = {
    "worker_id": "test-proxy-1",
    "miners": {"now": 5, "max": 10},
    "workers": 3,
    "hashrate": {"total": [5000.0, 10000.0]},
    "upstreams": {"active": 1, "total": 2, "ratio": 0.5},
    "results": {
        "accepted": 500,
        "rejected": 5,
        "invalid": 2,
        "expired": 1,
        "avg_time": 30,
        "latency": 25
    },
    "uptime": 7200
}


class TestBackwardCompatibility:
    """Test that single-target --url mode produces identical output"""

    def test_single_miner_no_extra_labels(self):
        """XmrigCollector with no extra_labels produces metrics without xmrig_target label"""
        families = {}
        extract_miner_metrics(MINER_RESPONSE, families, extra_labels=None)

        # Check that metrics exist
        assert "xmrig_hashrate0" in families
        assert "xmrig_shares_good" in families

        # Check that no xmrig_target label is present (only worker_id)
        hashrate_family = families["xmrig_hashrate0"]
        assert sorted(hashrate_family._labelnames) == ["worker_id"]

    def test_single_proxy_no_extra_labels(self):
        """XmrigProxyCollector with no extra_labels produces metrics without xmrig_target label"""
        families = {}
        extract_proxy_metrics(PROXY_RESPONSE, families, extra_labels=None)

        assert "xmrig_proxy_miners_now" in families
        miners_family = families["xmrig_proxy_miners_now"]
        assert sorted(miners_family._labelnames) == ["worker_id"]

    @patch('requests.get')
    def test_collector_backward_compatibility(self, mock_get):
        """XmrigCollector.collect() produces same output as before refactoring"""
        mock_response = Mock()
        mock_response.json.return_value = MINER_RESPONSE
        mock_get.return_value = mock_response

        collector = XmrigCollector("http://test.local/api", token=None)
        families = list(collector.collect())

        # Should have multiple families
        assert len(families) > 0

        # Check one metric has only worker_id label
        hashrate_families = [f for f in families if f.name == "xmrig_hashrate0"]
        assert len(hashrate_families) == 1
        assert sorted(hashrate_families[0]._labelnames) == ["worker_id"]


class TestMultiTargetSupport:
    """Test multi-target config with xmrig_target labels"""

    @patch('requests.get')
    def test_multi_target_adds_xmrig_target_label(self, mock_get):
        """MultiCollector adds xmrig_target label to all metrics"""
        mock_response = Mock()
        mock_response.json.return_value = MINER_RESPONSE
        mock_get.return_value = mock_response

        targets = [
            {"name": "rig-01", "url": "http://rig1.local/api", "mode": "miner"},
            {"name": "rig-02", "url": "http://rig2.local/api", "mode": "miner"}
        ]

        collector = MultiCollector(targets, timeout=5)
        families = list(collector.collect())

        # Find hashrate metric
        hashrate_families = [f for f in families if f.name == "xmrig_hashrate0"]
        assert len(hashrate_families) == 1

        # Should have both worker_id and xmrig_target labels
        assert sorted(hashrate_families[0]._labelnames) == ["worker_id", "xmrig_target"]

        # Should have 2 samples (one per target)
        assert len(hashrate_families[0].samples) == 2

    @patch('requests.get')
    def test_mixed_miner_and_proxy(self, mock_get):
        """MultiCollector handles mixed miner and proxy targets"""
        def mock_response_factory(url, **kwargs):
            mock = Mock()
            if "miner" in url:
                mock.json.return_value = MINER_RESPONSE
            else:
                mock.json.return_value = PROXY_RESPONSE
            return mock

        mock_get.side_effect = mock_response_factory

        targets = [
            {"name": "miner-01", "url": "http://miner.local/api", "mode": "miner"},
            {"name": "proxy-01", "url": "http://proxy.local/api", "mode": "proxy"}
        ]

        collector = MultiCollector(targets)
        families = list(collector.collect())

        # Should have both xmrig_ and xmrig_proxy_ prefixed metrics
        metric_names = [f.name for f in families]
        assert any("xmrig_hashrate" in name for name in metric_names)
        assert any("xmrig_proxy_miners" in name for name in metric_names)


class TestAutoDetection:
    """Test mode auto-detection"""

    @patch('requests.get')
    def test_auto_detect_proxy(self, mock_get):
        """Auto-detection identifies proxy when miners and workers keys present"""
        mock_response = Mock()
        mock_response.json.return_value = PROXY_RESPONSE
        mock_get.return_value = mock_response

        targets = [{"name": "target-01", "url": "http://test.local/api", "mode": "auto"}]
        collector = MultiCollector(targets)
        families = list(collector.collect())

        # Should have xmrig_proxy_ prefixed metrics
        metric_names = [f.name for f in families]
        assert any("xmrig_proxy_" in name for name in metric_names)

    @patch('requests.get')
    def test_auto_detect_miner(self, mock_get):
        """Auto-detection identifies miner when miners/workers keys absent"""
        mock_response = Mock()
        mock_response.json.return_value = MINER_RESPONSE
        mock_get.return_value = mock_response

        targets = [{"name": "target-01", "url": "http://test.local/api", "mode": "auto"}]
        collector = MultiCollector(targets)
        families = list(collector.collect())

        # Should have xmrig_ prefixed metrics (not xmrig_proxy_)
        metric_names = [f.name for f in families]
        assert any(name.startswith("xmrig_") and not name.startswith("xmrig_proxy_") for name in metric_names)


class TestFailureHandling:
    """Test error isolation and _up gauges"""

    @patch('requests.get')
    def test_one_failed_target_doesnt_break_others(self, mock_get):
        """One failed target doesn't prevent other targets from being scraped"""
        def mock_response_factory(url, **kwargs):
            if "bad" in url:
                raise Exception("Connection failed")
            mock = Mock()
            mock.json.return_value = MINER_RESPONSE
            return mock

        mock_get.side_effect = mock_response_factory

        targets = [
            {"name": "good-rig", "url": "http://good.local/api", "mode": "miner"},
            {"name": "bad-rig", "url": "http://bad.local/api", "mode": "miner"},
            {"name": "good-rig-2", "url": "http://good2.local/api", "mode": "miner"}
        ]

        collector = MultiCollector(targets)
        families = list(collector.collect())

        # Should have metrics from good targets
        assert len(families) > 0

        # Check _up gauge exists
        up_families = [f for f in families if f.name == "xmrig_up"]
        assert len(up_families) == 1

        # Should have 3 samples: 2 with value=1, 1 with value=0
        samples = up_families[0].samples
        assert len(samples) == 3

    @patch('requests.get')
    def test_up_gauge_zero_on_error(self, mock_get):
        """_up=0 emitted when target fails"""
        mock_get.side_effect = Exception("Network error")

        targets = [{"name": "failing-rig", "url": "http://fail.local/api", "mode": "miner"}]
        collector = MultiCollector(targets)
        families = list(collector.collect())

        # Should have _up gauge with value 0
        up_families = [f for f in families if f.name == "xmrig_up"]
        assert len(up_families) == 1
        assert len(up_families[0].samples) == 1
        assert up_families[0].samples[0].value == 0

    @patch('requests.get')
    def test_up_gauge_label_consistency_mixed_results(self, mock_get):
        """_up metric has consistent labels when some targets succeed and others fail"""
        def mock_response_factory(url, **kwargs):
            if "fail" in url:
                raise Exception("Network error")
            mock = Mock()
            mock.json.return_value = MINER_RESPONSE
            return mock

        mock_get.side_effect = mock_response_factory

        targets = [
            {"name": "good-rig", "url": "http://good.local/api", "mode": "miner"},
            {"name": "bad-rig", "url": "http://fail.local/api", "mode": "miner"}
        ]

        collector = MultiCollector(targets)
        families = list(collector.collect())

        # Find _up gauge
        up_families = [f for f in families if f.name == "xmrig_up"]
        assert len(up_families) == 1

        # All samples must have identical label names
        up_family = up_families[0]
        assert len(up_family.samples) == 2

        # Both samples should have same label names: worker_id and xmrig_target
        label_names_set = set(sorted(up_family._labelnames))
        assert label_names_set == {"worker_id", "xmrig_target"}

        # Check that failed target has worker_id='unknown'
        for sample in up_family.samples:
            if sample.value == 0:  # Failed target
                assert sample.labels.get("worker_id") == "unknown"


class TestMetricMerging:
    """Test metric merging across multiple targets"""

    def test_metric_merging_same_name_multiple_samples(self):
        """Multiple targets producing same metric name results in one MetricFamily with multiple samples"""
        families = {}

        # Simulate two targets with same metric
        extract_miner_metrics(
            MINER_RESPONSE,
            families,
            extra_labels={"xmrig_target": "rig-01"}
        )

        miner_response_2 = MINER_RESPONSE.copy()
        miner_response_2["worker_id"] = "test-miner-2"
        extract_miner_metrics(
            miner_response_2,
            families,
            extra_labels={"xmrig_target": "rig-02"}
        )

        # Should have only one MetricFamily for each metric name
        assert "xmrig_hashrate0" in families
        hashrate_family = families["xmrig_hashrate0"]

        # But it should have 2 samples (one per target)
        assert len(hashrate_family.samples) == 2

        # Samples should have different xmrig_target labels
        labels = [s.labels for s in hashrate_family.samples]
        targets = [l.get("xmrig_target") for l in labels]
        assert "rig-01" in targets
        assert "rig-02" in targets


class TestConfigParsing:
    """Test YAML config parsing and validation"""

    def test_valid_config_loads(self):
        """Valid YAML config loads successfully"""
        yaml_content = """
targets:
  - name: rig-01
    url: http://192.168.1.10:8080/1/summary
    mode: auto
  - name: proxy-01
    url: http://192.168.1.20:8080/1/summary
    token: secret
    mode: proxy
    timeout: 10
"""
        with patch('builtins.open', mock_open(read_data=yaml_content)):
            targets = load_config('/fake/path.yaml')

        assert len(targets) == 2
        assert targets[0]['name'] == 'rig-01'
        assert targets[0]['mode'] == 'auto'
        assert targets[1]['token'] == 'secret'
        assert targets[1]['timeout'] == 10

    def test_missing_file_raises_error(self):
        """Missing config file raises clear error"""
        with pytest.raises(ValueError, match="Config file not found"):
            load_config('/nonexistent/path.yaml')

    def test_invalid_yaml_raises_error(self):
        """Invalid YAML raises clear error"""
        with patch('builtins.open', mock_open(read_data="invalid: yaml: content:")):
            with pytest.raises(ValueError, match="Invalid YAML"):
                load_config('/fake/path.yaml')

    def test_missing_targets_key_raises_error(self):
        """Config without 'targets' key raises error"""
        with patch('builtins.open', mock_open(read_data="other_key: value")):
            with pytest.raises(ValueError, match="must have 'targets' key"):
                load_config('/fake/path.yaml')

    def test_missing_required_fields_raises_error(self):
        """Config with missing name/url raises error"""
        yaml_content = """
targets:
  - url: http://test.local
"""
        with patch('builtins.open', mock_open(read_data=yaml_content)):
            with pytest.raises(ValueError, match="missing required 'name' field"):
                load_config('/fake/path.yaml')

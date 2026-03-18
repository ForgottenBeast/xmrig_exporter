from .collector import XmrigCollector
from .proxy_collector import XmrigProxyCollector
from .multi_collector import MultiCollector
from .exporter import main

__version__ = "1.2.0"

# Backward compatibility
exporter_main = main

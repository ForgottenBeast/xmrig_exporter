from .collector import XmrigCollector
from .proxy_collector import XmrigProxyCollector
from .exporter import main

__version__ = "1.1.0"

# Backward compatibility
exporter_main = main

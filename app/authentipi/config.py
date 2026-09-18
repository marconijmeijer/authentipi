import os
from pathlib import Path

RULES_DIR = Path(os.environ.get("AUTHENTIPI_RULES_DIR", "/rules"))
DNS_LOG_PATH = Path(os.environ.get("AUTHENTIPI_DNS_LOG", "/var/log/dnsmasq/dnsmasq.log"))
DB_PATH = Path(os.environ.get("AUTHENTIPI_DB_PATH", "/data/authentipi.db"))

KNOWN_CATEGORIES = ["ai-text", "ai-image", "ai-video", "ai-audio", "ai-general"]

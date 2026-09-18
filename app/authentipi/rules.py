from __future__ import annotations

import logging
from dataclasses import dataclass

import yaml

from . import config

logger = logging.getLogger("authentipi.rules")


@dataclass(frozen=True)
class RuleEntry:
    domain: str
    service: str
    category: str
    source_list: str


class RuleSet:
    """In-memory index of domain -> RuleEntry, loaded from YAML files in
    config.RULES_DIR. Reload by re-instantiating or calling .load()."""

    def __init__(self) -> None:
        self._by_domain: dict[str, RuleEntry] = {}

    def load(self) -> None:
        entries: dict[str, RuleEntry] = {}
        if not config.RULES_DIR.exists():
            logger.warning("Rules dir %s does not exist", config.RULES_DIR)
            self._by_domain = entries
            return

        for path in sorted(config.RULES_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
            except yaml.YAMLError:
                logger.exception("Failed to parse rules file %s", path)
                continue

            list_name = data.get("name", path.stem)
            for raw in data.get("entries", []):
                domain = str(raw.get("domain", "")).strip().lower()
                if not domain:
                    continue
                entries[domain] = RuleEntry(
                    domain=domain,
                    service=str(raw.get("service", "unknown")),
                    category=str(raw.get("category", "ai-general")),
                    source_list=list_name,
                )

        logger.info("Loaded %d domain rules from %s", len(entries), config.RULES_DIR)
        self._by_domain = entries

    def match(self, domain: str) -> RuleEntry | None:
        return self._by_domain.get(domain.strip().lower().rstrip("."))

    def all_entries(self) -> list[RuleEntry]:
        return sorted(self._by_domain.values(), key=lambda e: e.domain)

    def categories(self) -> list[str]:
        return sorted({e.category for e in self._by_domain.values()})


ruleset = RuleSet()

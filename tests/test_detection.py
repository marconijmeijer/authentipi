"""
Integration tests against a running AuthentiPi stack (docker compose up -d).

Elk testgeval doet een echte DNS-query via de dnsmasq-container en checkt via
de API of dat wel/niet tot een detectie leidt. Nieuwe AI-diensten testen?
Voeg een entry toe aan rules/default.yaml en een bijbehorende test hieronder.
"""

from helpers import (
    dns_query,
    get_category_enabled,
    latest_detection_id,
    set_category,
    wait_for_new_detection,
)


def test_known_ai_domain_produces_a_detection():
    since_id = latest_detection_id()
    dns_query("runwayml.com")

    detection = wait_for_new_detection("runwayml.com", since_id)

    assert detection is not None, "verwachtte een detectie voor runwayml.com"
    assert detection["service"] == "Runway"
    assert detection["category"] == "ai-video"


def test_unrelated_domain_produces_no_detection():
    since_id = latest_detection_id()
    dns_query("example.com")

    detection = wait_for_new_detection("example.com", since_id, timeout=3)

    assert detection is None, "example.com staat niet in de regellijst"


def test_disabling_a_category_suppresses_new_detections():
    was_enabled = get_category_enabled("ai-audio")
    set_category("ai-audio", False)
    try:
        since_id = latest_detection_id()
        dns_query("elevenlabs.io")

        detection = wait_for_new_detection("elevenlabs.io", since_id, timeout=3)

        assert detection is None, "categorie 'ai-audio' stond uit"
    finally:
        set_category("ai-audio", was_enabled)


def test_re_enabling_a_category_allows_detections_again():
    set_category("ai-audio", True)
    since_id = latest_detection_id()
    dns_query("elevenlabs.io")

    detection = wait_for_new_detection("elevenlabs.io", since_id)

    assert detection is not None
    assert detection["category"] == "ai-audio"

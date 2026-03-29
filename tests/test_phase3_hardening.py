import logging

from polla_app.exceptions import ScriptError
from polla_app.obs import sanitize
from polla_app.pipeline import _merge_pozos


def test_contextual_redaction_logic():
    # Long strings should NOT be redacted if the key is safe
    safe_data = {
        "url": "https://example.com/very/long/path/that/used/to/be/redacted/because/of/length"
    }
    sanitized_safe = sanitize(safe_data)
    assert sanitized_safe["url"] == safe_data["url"]

    # Sensitive keys SHOULD be redacted regardless of value length (if > 6)
    sensitive_data = {"api_key": "secret-123456-token"}
    sanitized_sensitive = sanitize(sensitive_data)
    assert sanitized_sensitive["api_key"] != sensitive_data["api_key"]
    assert "…" in sanitized_sensitive["api_key"]


def test_script_error_logs_are_sanitized(caplog):
    caplog.set_level(logging.ERROR)
    logger = logging.getLogger("test_logger")

    err = ScriptError("Failed", context={"secret_token": "super-secret-payload"})
    err.log_error(logger)

    # Check that the log output is sanitized
    assert "super-secret-payload" not in caplog.text
    assert "supe…ad" in caplog.text


def test_magnitude_quarantine_calculation():
    collected = [
        {"fuente": "A", "montos": {"Loto": 1000}},
        {"fuente": "B", "montos": {"Loto": 1010}},  # 1% deviation
        {"fuente": "C", "montos": {"Loto": 1150}},  # 15% deviation
    ]

    resolved, provenance, mismatches = _merge_pozos(collected)

    # Winner should be 1000 or 1010 (based on votes/order if tie)
    # But here they are all different votes (1 each)
    # Sorted by votes descending: all tied. Sorted by value? No, just order.
    # Winner will likely be 1000.

    assert len(mismatches) == 1
    m = mismatches[0]
    # Max deviation between 1000 and 1150 is 15% (0.15)
    assert m["max_deviation"] >= 0.14

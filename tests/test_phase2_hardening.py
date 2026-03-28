import os
import pytest
import requests
from polla_app import net
from polla_app import pipeline

def test_fetch_html_exponential_backoff(monkeypatch):
    url = "https://example.test/429"
    ua = "test-bot"
    
    # Mock sequence: 429, 429, 200
    class MockResponse:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

    responses_queue = [
        MockResponse(429),
        MockResponse(429),
        MockResponse(200, "<html>success</html>")
    ]

    def mock_get(self, url, **kwargs):
        return responses_queue.pop(0)

    monkeypatch.setattr(requests.Session, "get", mock_get)
    # Mock robots to always allow
    monkeypatch.setattr(net, "_robots_allowed", lambda url, ua: True)
    
    # Configure fast backoff for testing
    monkeypatch.setenv("POLLA_MAX_RETRIES", "3")
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.1")
    
    # Mock time.sleep to avoid waiting
    sleep_calls = []
    monkeypatch.setattr(net.time, "sleep", lambda x: sleep_calls.append(x))
    
    metadata = net.fetch_html(url, ua=ua)
    
    assert metadata.html == "<html>success</html>"
    assert len(sleep_calls) == 2
    # Check exponential growth (with jitter)
    assert sleep_calls[0] >= 0.1
    assert sleep_calls[1] >= 0.2
    assert sleep_calls[1] > sleep_calls[0]

def test_source_registry_unification():
    # Verify that all expected sources are in the registry
    expected = {"pozos", "resultadoslotochile", "openloto"}
    assert expected.issubset(pipeline.SOURCE_LOADERS.keys())
    
    # Verify that requesting 'resultadoslotochile' works and uses the registry
    sources = pipeline._normalize_sources(["resultadoslotochile"])
    assert sources == ["resultadoslotochile"]

def test_deprecated_internal_alias_is_commented_out():
    # Verify the internal alias was removed from the namespace
    assert not hasattr(pipeline, "_normalise_sources")

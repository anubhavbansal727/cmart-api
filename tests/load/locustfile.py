"""Locust load test — verifies 100 req/min rate limit holds under concurrent load.

Usage:
    locust -f tests/load/locustfile.py --host http://localhost:8000

Set CMART_TEST_API_KEY env var to match the key in your .env / Railway environment.
"""
from __future__ import annotations

import os

from locust import HttpUser, between, task

_API_KEY = os.getenv("CMART_TEST_API_KEY", "test-key")
_HEADERS = {"Authorization": f"Bearer {_API_KEY}"}


class CMARTQueryUser(HttpUser):
    """Simulates a typical API client sending support queries."""

    wait_time = between(0.5, 1.0)  # ~60–120 req/min per user

    @task(4)
    def query_clear(self) -> None:
        self.client.post(
            "/query",
            headers=_HEADERS,
            json={
                "query": "How do I reset my password?",
                "user_id": "load-test-user",
            },
            name="/query [clear]",
        )

    @task(2)
    def query_ambiguous(self) -> None:
        self.client.post(
            "/query",
            headers=_HEADERS,
            json={
                "query": "Something is broken",
                "user_id": "load-test-user",
            },
            name="/query [ambiguous]",
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="/health")

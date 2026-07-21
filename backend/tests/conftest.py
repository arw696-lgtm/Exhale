"""Shared test plumbing."""

import pytest

from exhale.api import rate_limiter


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    """Every TestClient request comes from the same 'testclient' IP, so the
    auth/OAuth limiter must not accumulate hits across unrelated tests."""

    rate_limiter.reset()
    yield
    rate_limiter.reset()

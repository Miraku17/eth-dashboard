"""Unit tests for app.services.mnt_price.

The function under test is a thin Redis-cached HTTP wrapper, so the
tests stub both the cache helpers and the HTTP client and only assert
the wiring."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.mnt_price import get_mnt_usd, MNT_PRICE_CACHE_KEY


def test_returns_cached_value_when_redis_hits():
    with patch("app.services.mnt_price.cached_json_get", return_value=0.81) as mock_get:
        assert get_mnt_usd() == pytest.approx(0.81)
    mock_get.assert_called_once_with(MNT_PRICE_CACHE_KEY)


def test_fetches_and_caches_on_miss():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"mantle": {"usd": 0.79}}
    with (
        patch("app.services.mnt_price.cached_json_get", return_value=None),
        patch("app.services.mnt_price.cached_json_set") as mock_set,
        patch("app.services.mnt_price.httpx.get", return_value=mock_resp) as mock_http,
    ):
        assert get_mnt_usd() == pytest.approx(0.79)
    mock_http.assert_called_once()
    # Redis SET with the 60s TTL
    mock_set.assert_called_once_with(MNT_PRICE_CACHE_KEY, 0.79, 60)


def test_returns_none_on_http_error():
    mock_resp = MagicMock(status_code=429)
    mock_resp.json.return_value = {}
    with (
        patch("app.services.mnt_price.cached_json_get", return_value=None),
        patch("app.services.mnt_price.cached_json_set") as mock_set,
        patch("app.services.mnt_price.httpx.get", return_value=mock_resp),
    ):
        assert get_mnt_usd() is None
    # Negative result is NOT cached.
    mock_set.assert_not_called()


def test_returns_none_on_network_exception():
    import httpx
    with (
        patch("app.services.mnt_price.cached_json_get", return_value=None),
        patch("app.services.mnt_price.cached_json_set") as mock_set,
        patch("app.services.mnt_price.httpx.get", side_effect=httpx.RequestError("boom")),
    ):
        assert get_mnt_usd() is None
    mock_set.assert_not_called()

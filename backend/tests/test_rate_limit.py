"""Per-IP login rate limit."""
import pytest

from app.core import rate_limit


def test_under_limit_does_not_block(migrated_engine):
    for _ in range(rate_limit.MAX_FAILURES):
        rate_limit.register_login_failure("1.2.3.4")
    # Up to MAX_FAILURES is allowed (the next attempt is the one that trips).
    rate_limit.check_login_ip("1.2.3.4")  # must not raise


def test_over_limit_raises(migrated_engine):
    for _ in range(rate_limit.MAX_FAILURES + 1):
        rate_limit.register_login_failure("1.2.3.4")
    with pytest.raises(rate_limit.RateLimited) as exc:
        rate_limit.check_login_ip("1.2.3.4")
    assert exc.value.retry_after_seconds > 0


def test_isolated_per_ip(migrated_engine):
    for _ in range(rate_limit.MAX_FAILURES + 1):
        rate_limit.register_login_failure("1.2.3.4")
    # Different IP is unaffected.
    rate_limit.check_login_ip("9.9.9.9")

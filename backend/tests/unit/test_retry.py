from callwise.reliability.retry import RetryClass, classify_error, classify_reason


def test_terminal_reason_never_retries():
    assert classify_reason("invalid_number") is RetryClass.terminal
    assert classify_reason("dnd") is RetryClass.terminal


def test_retryable_reason():
    assert classify_reason("rate_limited") is RetryClass.retryable
    assert classify_reason("busy") is RetryClass.retryable


def test_unknown_reason_fails_safe_to_terminal():
    # Don't burn credits on an unclassified error — fail safe, surface via DLQ/alerts.
    assert classify_reason("something_new") is RetryClass.terminal
    assert classify_reason(None) is RetryClass.terminal


def test_classify_5xx_is_retryable():
    exc = Exception()
    exc.status_code = 503  # type: ignore[attr-defined]
    assert classify_error(exc) is RetryClass.retryable


def test_classify_timeout_is_retryable():
    assert classify_error(TimeoutError()) is RetryClass.retryable

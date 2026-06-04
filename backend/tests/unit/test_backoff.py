from callwise.reliability.backoff import next_backoff


def test_backoff_is_positive():
    assert next_backoff(1) > 0


def test_backoff_respects_cap_with_jitter():
    cap = 300.0
    # raw is capped at `cap`; full jitter widens by at most (1 + jitter).
    for attempt in range(1, 15):
        assert next_backoff(attempt, cap=cap, jitter=0.3) <= cap * 1.3


def test_backoff_grows_then_saturates():
    # Averaged over jitter, later attempts are not smaller than the cap floor.
    low = sum(next_backoff(1) for _ in range(50)) / 50
    high = sum(next_backoff(10) for _ in range(50)) / 50
    assert high > low

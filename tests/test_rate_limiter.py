from oluso.rate_limiter import RateLimiter


def test_allows_sends_under_limit():
    rl = RateLimiter(3)
    assert rl.can_send()
    assert rl.can_send()
    assert rl.can_send()
    assert rl.count() == 3


def test_blocks_once_limit_reached():
    rl = RateLimiter(2)
    assert rl.can_send()
    assert rl.can_send()
    assert not rl.can_send()
    assert rl.count() == 2


def test_allows_again_after_window_passes():
    now = [0.0]
    rl = RateLimiter(1, now=lambda: now[0])

    assert rl.can_send()
    assert not rl.can_send()

    now[0] = 61.0
    assert rl.can_send()


def test_reset_clears_tracked_timestamps():
    rl = RateLimiter(1)
    assert rl.can_send()
    assert not rl.can_send()
    rl.reset()
    assert rl.can_send()

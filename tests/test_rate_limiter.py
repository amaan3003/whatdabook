import unittest

from rate_limiter import SlidingWindowRateLimiter


class SlidingWindowRateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.limiter = SlidingWindowRateLimiter(limit=7, window_seconds=60)

    def test_allows_seven_actions_then_blocks_the_eighth(self):
        for second in range(7):
            self.assertEqual(self.limiter.check(101, now=second), (True, 0))

        self.assertEqual(self.limiter.check(101, now=7), (False, 53))

    def test_allows_another_action_when_oldest_event_expires(self):
        for second in range(7):
            self.limiter.check(101, now=second)

        self.assertEqual(self.limiter.check(101, now=60), (True, 0))

    def test_tracks_each_user_separately(self):
        for second in range(7):
            self.limiter.check(101, now=second)

        self.assertEqual(self.limiter.check(101, now=7), (False, 53))
        self.assertEqual(self.limiter.check(202, now=7), (True, 0))

    def test_blocked_attempt_does_not_extend_the_window(self):
        for second in range(7):
            self.limiter.check(101, now=second)

        self.limiter.check(101, now=20)
        self.assertEqual(self.limiter.check(101, now=60), (True, 0))


if __name__ == "__main__":
    unittest.main()

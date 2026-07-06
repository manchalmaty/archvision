import pytest
from fastapi.testclient import TestClient

from config import settings
from core.ratelimit import SlidingWindowLimiter, limiter
from main import app

client = TestClient(app)

PARAMS = {
    "rooms": [
        {"room_type": "living_room", "area_m2": 18},
        {"room_type": "kitchen", "area_m2": 9},
        {"room_type": "bathroom", "area_m2": 4},
        {"room_type": "hallway", "area_m2": 5},
    ],
    "country": "RU",
    "floors": 1,
    "building_shape": "rectangular",
}


class TestSlidingWindow:
    def test_allows_up_to_limit_then_rejects_with_retry_after(self):
        lim = SlidingWindowLimiter()
        limits = [(3, 60)]
        assert lim.check("k", limits, now=100.0) == 0.0
        assert lim.check("k", limits, now=101.0) == 0.0
        assert lim.check("k", limits, now=102.0) == 0.0
        retry = lim.check("k", limits, now=103.0)
        assert retry == pytest.approx(57.0)  # oldest event (100) + 60 - 103

    def test_window_slides(self):
        lim = SlidingWindowLimiter()
        limits = [(1, 60)]
        assert lim.check("k", limits, now=0.0) == 0.0
        assert lim.check("k", limits, now=30.0) > 0
        assert lim.check("k", limits, now=61.0) == 0.0

    def test_rejection_records_nothing(self):
        # Probing while limited must not extend the ban.
        lim = SlidingWindowLimiter()
        limits = [(1, 60)]
        assert lim.check("k", limits, now=0.0) == 0.0
        for t in (10.0, 20.0, 30.0):
            assert lim.check("k", limits, now=t) > 0
        assert lim.check("k", limits, now=60.5) == 0.0

    def test_multiple_windows_checked_atomically(self):
        lim = SlidingWindowLimiter()
        limits = [(2, 60), (3, 86400)]
        assert lim.check("k", limits, now=0.0) == 0.0
        assert lim.check("k", limits, now=1.0) == 0.0
        # Minute window full → rejected; day window must NOT record the probe.
        assert lim.check("k", limits, now=2.0) > 0
        # Minute window freed → the day window has 2 events, one slot left.
        assert lim.check("k", limits, now=62.0) == 0.0
        assert lim.check("k", limits, now=63.0) > 0  # now the day window is full

    def test_keys_are_independent(self):
        lim = SlidingWindowLimiter()
        limits = [(1, 60)]
        assert lim.check("a", limits, now=0.0) == 0.0
        assert lim.check("b", limits, now=0.0) == 0.0

    def test_zero_limit_disables_window(self):
        lim = SlidingWindowLimiter()
        for t in range(10):
            assert lim.check("k", [(0, 60)], now=float(t)) == 0.0


class TestGenerateEndpointLimit:
    @pytest.fixture(autouse=True)
    def tight_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
        limiter.reset()
        yield
        limiter.reset()  # don't bleed events into other test modules

    def test_second_request_is_429_with_retry_after(self):
        first = client.post("/api/v1/generate-plan", json=PARAMS)
        assert first.status_code == 200
        second = client.post("/api/v1/generate-plan", json=PARAMS)
        assert second.status_code == 429
        assert int(second.headers["Retry-After"]) >= 1

    def test_validation_errors_do_not_consume_the_budget(self):
        bad = client.post("/api/v1/generate-plan", json={**PARAMS, "rooms": []})
        assert bad.status_code == 422
        ok = client.post("/api/v1/generate-plan", json=PARAMS)
        assert ok.status_code == 200

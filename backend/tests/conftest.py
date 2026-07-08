"""
Shared pytest fixtures. Environment is pinned BEFORE any app import:
config.Settings is cached at module import, so these must run first.
"""

import os
import sys
import tempfile

# Keep tests offline and side-effect free.
os.environ["GROQ_API_KEY"] = ""
os.environ["IFC_OUTPUT_DIR"] = tempfile.mkdtemp(prefix="archvision_test_")

# Make `models`, `core.*`, `api.*` importable when pytest runs from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core.ratelimit import limiter  # noqa: E402
from models import BuildingParams, RoomInput, RoomType  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test starts with a clean limiter, so the in-process daily window
    can't accumulate across the suite and 429 a later route test (the whole
    suite shares one client IP). Tests that exercise the limiter make their own
    burst within the test, so resetting beforehand is safe."""
    limiter.reset()
    yield


@pytest.fixture
def basic_params() -> BuildingParams:
    """A representative 6-room single-floor request."""
    return BuildingParams(
        rooms=[
            RoomInput(room_type=RoomType.LIVING_ROOM, area_m2=20),
            RoomInput(room_type=RoomType.BEDROOM, area_m2=14),
            RoomInput(room_type=RoomType.KITCHEN, area_m2=10),
            RoomInput(room_type=RoomType.BATHROOM, area_m2=5),
            RoomInput(room_type=RoomType.TOILET, area_m2=2),
            RoomInput(room_type=RoomType.HALLWAY, area_m2=6),
        ],
        country="KZ",
        floors=1,
        building_shape="rectangular",
    )


def rooms_overlap(a, b) -> bool:
    """AABB overlap test for two RoomLayout objects on the same floor."""
    if a.floor != b.floor:
        return False
    eps = 0.01
    separated = (
        a.x + a.width <= b.x + eps
        or b.x + b.width <= a.x + eps
        or a.y + a.depth <= b.y + eps
        or b.y + b.depth <= a.y + eps
    )
    return not separated

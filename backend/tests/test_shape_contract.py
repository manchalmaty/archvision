"""The building_shape API contract is honest: rectangular | square only.

The engine tiles a central-hall RECTANGLE for every shape — the l/u/t values
were silent aliases for near-identical aspect ratios (1.3–1.45), so the public
API promised silhouettes it never produced. Unknown values must be rejected
loudly, not flattened into a rectangle behind the caller's back. Real L/U/T
footprints are a roadmap item, to be reintroduced as honest new values.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.layout_engine import LayoutEngine
from main import app
from models import BuildingParams, RoomInput, RoomType

client = TestClient(app)


@pytest.mark.parametrize("legacy", ["l_shape", "u_shape", "t_shape"])
def test_legacy_silhouette_values_rejected(legacy):
    with pytest.raises(ValidationError):
        BuildingParams(
            rooms=[RoomInput(room_type=RoomType.BEDROOM, area_m2=15)],
            country="KZ",
            floors=1,
            building_shape=legacy,
        )


def test_api_rejects_unknown_shape_with_422():
    r = client.post(
        "/api/v1/generate-plan",
        json={
            "rooms": [{"room_type": "bedroom", "area_m2": 15}],
            "country": "KZ",
            "floors": 1,
            "building_shape": "l_shape",
        },
    )
    assert r.status_code == 422


def test_shape_aspect_table_matches_contract():
    # The engine's aspect table and the API contract must not drift apart.
    assert set(LayoutEngine._SHAPE_ASPECT) == {"rectangular", "square"}

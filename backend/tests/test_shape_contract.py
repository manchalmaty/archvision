"""The building_shape API contract is honest: a value exists only if it tiles.

rectangular|square are proportions of the central-hall bar; l_shape became a
REAL two-wing silhouette in release 6. u/t remain rejected — they were silent
aliases for near-identical aspect ratios and will return as honest new values
only when they truly tile (courtyard perimeter breaks the cost model today).
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.layout_engine import LayoutEngine
from main import app
from models import BuildingParams, RoomInput, RoomType

client = TestClient(app)


@pytest.mark.parametrize("legacy", ["u_shape", "t_shape"])
def test_untileable_silhouette_values_rejected(legacy):
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
            "building_shape": "u_shape",
        },
    )
    assert r.status_code == 422


def test_shape_aspect_table_matches_contract():
    # The aspect table holds the RECTANGLE proportions; l_shape is a composer,
    # not an aspect. Together they must equal the API pattern exactly.
    assert set(LayoutEngine._SHAPE_ASPECT) | {"l_shape"} == {
        "rectangular",
        "square",
        "l_shape",
    }

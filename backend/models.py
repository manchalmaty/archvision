from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class CountryCode(str, Enum):
    RU = "RU"
    KZ = "KZ"
    UA = "UA"
    BY = "BY"
    UZ = "UZ"
    DE = "DE"
    US = "US"
    OTHER = "OTHER"


class RoomType(str, Enum):
    BEDROOM = "bedroom"
    LIVING_ROOM = "living_room"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    TOILET = "toilet"
    HALLWAY = "hallway"
    UTILITY = "utility"
    GARAGE = "garage"


class RoomInput(BaseModel):
    room_type: RoomType
    area_m2: float = Field(gt=0, le=200)
    name: Optional[str] = None


class BuildingParams(BaseModel):
    rooms: List[RoomInput] = Field(min_length=1, max_length=30)
    country: CountryCode
    region: Optional[str] = None
    floors: int = Field(ge=1, le=5)
    plot_width_m: Optional[float] = Field(default=None, gt=0)
    plot_depth_m: Optional[float] = Field(default=None, gt=0)
    building_shape: str = "rectangular"  # rectangular|square|l_shape|u_shape|t_shape


class GeoClimateData(BaseModel):
    frost_depth_m: float
    foundation_type: str
    seismic_zone: int
    max_floors_seismic: int
    wall_thickness_mm: int
    insulation_thickness_mm: int
    snow_load_kpa: float
    wind_load_kpa: float


class DoorSpec(BaseModel):
    wall: str        # 'N' | 'S' | 'E' | 'W'
    position: float  # offset from west/south corner (m)
    width: float = 0.8
    height: float = 2.0


class WindowSpec(BaseModel):
    wall: str
    position: float
    width: float = 1.2
    height: float = 1.0
    sill: float = 0.9


class RoomLayout(BaseModel):
    room_id: str
    room_type: RoomType
    name: str
    x: float
    y: float
    floor: int
    width: float
    depth: float
    area_m2: float
    doors: List[DoorSpec] = []
    windows: List[WindowSpec] = []


class MEPConflict(BaseModel):
    conflict_id: str
    conflict_type: str
    description: str
    location_x: float
    location_y: float
    location_z: float
    severity: str


class ComplianceIssue(BaseModel):
    rule_id: str
    description: str
    severity: str
    room_id: Optional[str] = None
    suggested_fix: Optional[str] = None


class CostEstimate(BaseModel):
    concrete_m3: float
    brick_m3: float
    insulation_m2: float
    total_cost_usd: float
    total_cost_local: float
    currency: str
    breakdown: dict


class GenerationResult(BaseModel):
    project_id: str
    rooms: List[RoomLayout]
    geo_climate: GeoClimateData
    mep_conflicts: List[MEPConflict]
    compliance_issues: List[ComplianceIssue]
    cost_estimate: CostEstimate
    ifc_file_url: str
    warnings: List[str]


class ComplianceRequest(BaseModel):
    country: CountryCode
    rooms: List[RoomInput]
    floors: int


class MEPRoutingRequest(BaseModel):
    project_id: str
    rooms: List[RoomLayout]
    floors: int

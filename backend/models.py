from enum import Enum

from pydantic import BaseModel, Field


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
    name: str | None = None


class BuildingParams(BaseModel):
    rooms: list[RoomInput] = Field(min_length=1, max_length=30)
    country: CountryCode
    region: str | None = None
    floors: int = Field(ge=1, le=5)
    plot_width_m: float | None = Field(default=None, gt=0)
    plot_depth_m: float | None = Field(default=None, gt=0)
    # Honest silhouettes only: rectangular/square proportions of the central-
    # hall bar, a REAL L (release 6, two-storey since release 10) and a REAL T
    # (release 11: two wings + entrance stem; perimeter == bbox by monotonicity,
    # so the cost model stays exact). U stays out: its courtyard makes the
    # exterior LONGER than the bbox, which the cost model cannot price yet.
    building_shape: str = Field(
        default="rectangular", pattern="^(rectangular|square|l_shape|t_shape)$"
    )
    # Openness of the social zone (a preference, not an invariant):
    #   closed — every room walled, kitchen on the wet riser, entrance via hallway
    #   mixed  — kitchen+living open as one volume, bedrooms behind a hallway
    #   open   — kitchen+living open, no hallway; entrance into the social volume
    openness: str = "closed"  # closed|mixed|open
    # Budget ↔ spacious (a single preference): 0 = compact + small rooms (cheap),
    # 1 = spread + large rooms (pricey). 0.5 = neutral (current behavior).
    spaciousness: float = Field(default=0.5, ge=0.0, le=1.0)
    # Real compass bearing the plan's top ("N" wall) points to. A SENSOR input:
    # it never moves rooms, only scores daylight (and drives whole-plan rotation
    # when auto_orient is on). 8-point: N|NE|E|SE|S|SW|W|NW. "N" = top is north.
    facing: str = "N"
    # When true, rotate the finished plan to the quarter-turn that best faces
    # rooms to the sun (actuator). The solver stays sun-blind; this is on top.
    auto_orient: bool = False
    # Which plot edge abuts the street (red line). Drives the larger front
    # setback; the other three edges get the neighbour setback. S = the plan's
    # front (min-y / bottom) faces the street — the natural default.
    street_side: str = "S"  # S|N|E|W


class GeoClimateData(BaseModel):
    frost_depth_m: float
    foundation_type: str
    seismic_zone: int
    max_floors_seismic: int
    wall_thickness_mm: int
    insulation_thickness_mm: int
    snow_load_kpa: float
    wind_load_kpa: float
    # Design winter temperature DERIVED from the same climate index (AFI) that
    # drives frost depth — a draft figure, not a СП 131 lookup. None on results
    # stored before the heating layer existed.
    design_temp_c: float | None = None


class DoorSpec(BaseModel):
    wall: str  # 'N' | 'S' | 'E' | 'W'
    position: float  # offset from west/south corner (m)
    width: float = 0.8
    height: float = 2.0
    kind: str = "door"  # "door" (swing leaf) | "opening" (cased gap) | "gate" (vehicle panel)


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
    doors: list[DoorSpec] = []
    windows: list[WindowSpec] = []
    # Daylight rating for this room given the building's facing: "good" | "ok" |
    # "poor" for habitable rooms, "" for rooms that don't need sun. A sensor
    # annotation — set after layout, never affects placement.
    sun: str = ""
    # Net (usable) dimensions after wall thicknesses: exterior walls grow inward
    # from the axis line (the bbox stays the real outer footprint), interior
    # partitions take half each side. Annotation only — the axis figure stays
    # the primary single definition. None on pre-release-5 stored results.
    net_width: float | None = None
    net_depth: float | None = None
    net_area: float | None = None


class SitePlan(BaseModel):
    """The building placed on its plot, with the setback / coverage figures.

    Offsets translate the plan (whose ground floor is anchored at the origin)
    into the plot's coordinate frame; clearances are the actual metres of yard
    on each compass edge. All figures are honest w×d geometry, matching the rest
    of the app — nothing here subtracts wall thickness.
    """

    plot_width_m: float
    plot_depth_m: float
    building_width_m: float
    building_depth_m: float
    offset_x: float
    offset_y: float
    street_side: str  # S|N|E|W
    street_setback_m: float
    neighbor_setback_m: float
    clearances: dict[str, float]  # {"S","N","W","E"} → yard metres on that edge
    coverage_ratio: float
    coverage_limit: float
    seismic_zone: int
    seismic_flag: bool


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
    room_id: str | None = None
    suggested_fix: str | None = None


class CostEstimate(BaseModel):
    concrete_m3: float
    brick_m3: float
    insulation_m2: float
    total_cost_usd: float
    total_cost_local: float
    currency: str
    breakdown: dict


class PlanVariant(BaseModel):
    """One row of the cost-Δ decision table.

    The same room program re-tiled by the DETERMINISTIC rule engine at a fixed
    spaciousness setting — never the LLM, so every figure is reproducible.
    Deltas are vs the cheapest row; delta_driver names the dominant material
    system behind that delta ("concrete" | "walls").
    """

    label: str  # compact | balanced | roomy
    spaciousness: float
    footprint_m2: float  # Σ w×d over all floors — the same figure the штамп shows
    concrete_m3: float
    brick_m3: float
    total_cost_local: float
    total_cost_usd: float
    currency: str
    delta_local: float = 0.0
    delta_usd: float = 0.0
    delta_footprint_m2: float = 0.0
    delta_concrete_m3: float = 0.0
    delta_driver: str = ""  # "" on the cheapest row
    # ERROR-severity invariant + site violations on the re-tiled plan: a cheaper
    # row that breaks minimum room sizes must say so in the row that tempts.
    red_flags: int = 0


class HeatingEstimate(BaseModel):
    """Sketch-level design heat loss (U-value envelope method) + boiler sizing.

    Honest draft, same contract as the cost model: real geo-driven wall and
    insulation thicknesses, the cost model's 30% window fraction, ventilation
    air change. NOT a thermal engineering calculation (СП 50) — the figure
    exists so the heating conversation with an engineer starts earlier.
    """

    design_temp_c: float
    heated_area_m2: float  # garage excluded — it is an unheated buffer
    heat_loss_kw: float
    specific_w_m2: float
    boiler_kw: float


class GenerationResult(BaseModel):
    project_id: str
    rooms: list[RoomLayout]
    geo_climate: GeoClimateData
    mep_conflicts: list[MEPConflict]
    compliance_issues: list[ComplianceIssue]
    cost_estimate: CostEstimate
    ifc_file_url: str
    warnings: list[str]
    # Overall daylight score 0..100 for the chosen facing (sensor).
    insolation_score: float = 0.0
    # Plot placement + setback/coverage figures. Present only when a plot size
    # was given; None otherwise (the tool still works with no plot).
    site: SitePlan | None = None
    # False when the typed region did not match the climate index: the geo/seismic
    # figures are then the country AVERAGE, which for an unlisted high-seismic town
    # reads dangerously low. Surfaces an "unverified seismicity" caveat so the
    # number never looks authoritative — fail loud, not low.
    region_recognized: bool = True
    # Cost-Δ decision table, sorted by cost ascending. Default [] keeps
    # pre-variants stored results loadable.
    variants: list[PlanVariant] = []
    # Draft heat-loss + boiler sizing. None on pre-heating stored results.
    heating: HeatingEstimate | None = None


class ComplianceRequest(BaseModel):
    country: CountryCode
    rooms: list[RoomInput]
    floors: int


class MEPRoutingRequest(BaseModel):
    project_id: str
    rooms: list[RoomLayout]
    floors: int

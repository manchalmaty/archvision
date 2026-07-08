export type RoomType =
  | "bedroom"
  | "living_room"
  | "kitchen"
  | "bathroom"
  | "toilet"
  | "hallway"
  | "utility"
  | "garage";

export type CountryCode = "RU" | "KZ" | "UA" | "BY" | "UZ" | "DE" | "US" | "OTHER";

export type Facing = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

export interface RoomInput {
  room_type: RoomType;
  area_m2: number;
  name?: string;
}

export type BuildingShape = "rectangular" | "square" | "l_shape" | "u_shape" | "t_shape";

// Social-zone openness (a preference): closed = every room walled; mixed =
// kitchen+living open as one volume but bedrooms behind a hallway; open = no
// hallway, entrance into the social volume.
export type Openness = "closed" | "mixed" | "open";

export interface BuildingParams {
  rooms: RoomInput[];
  country: CountryCode;
  region?: string;
  floors: number;
  plot_width_m?: number;
  plot_depth_m?: number;
  building_shape: BuildingShape;
  openness: Openness;
  // Budget ↔ spacious (0..1): 0 = compact + small rooms (cheap), 1 = spread +
  // large rooms (pricey). 0.5 = neutral.
  spaciousness: number;
  facing: Facing;
  // Auto-rotate the finished plan to the orientation with the best daylight.
  auto_orient: boolean;
  // Which plot edge abuts the street (red line) — drives the larger front
  // setback; the other three edges get the neighbour setback. S = plan front.
  street_side: "S" | "N" | "W" | "E";
}

export interface GeoClimateData {
  frost_depth_m: number;
  foundation_type: string;
  seismic_zone: number;
  max_floors_seismic: number;
  wall_thickness_mm: number;
  insulation_thickness_mm: number;
  snow_load_kpa: number;
  wind_load_kpa: number;
}

export interface DoorSpec {
  wall: "N" | "S" | "E" | "W";
  position: number;
  width: number;
  height: number;
  // "opening" = a wide cased gap (no swing leaf), used for the open kitchen↔living
  // boundary; "gate" = a garage vehicle gate (straight panel, no swing);
  // "door" (or absent) = a normal hinged door.
  kind?: "door" | "opening" | "gate";
}

export interface WindowSpec {
  wall: "N" | "S" | "E" | "W";
  position: number;
  width: number;
  height: number;
  sill: number;
}

export interface RoomLayout {
  room_id: string;
  room_type: RoomType;
  name: string;
  x: number;
  y: number;
  floor: number;
  width: number;
  depth: number;
  area_m2: number;
  doors: DoorSpec[];
  windows: WindowSpec[];
  sun?: "good" | "ok" | "poor" | "";
}

export interface MEPConflict {
  conflict_id: string;
  conflict_type: string;
  description: string;
  location_x: number;
  location_y: number;
  location_z: number;
  severity: "HIGH" | "MEDIUM" | "LOW";
}

export interface ComplianceIssue {
  rule_id: string;
  description: string;
  severity: "ERROR" | "WARNING" | "INFO";
  room_id?: string;
  suggested_fix?: string;
}

export interface CostEstimate {
  concrete_m3: number;
  brick_m3: number;
  insulation_m2: number;
  total_cost_usd: number;
  total_cost_local: number;
  currency: string;
  breakdown: Record<string, number>;
}

export interface ProjectSummary {
  project_id: string;
  created_at: string;
  rooms: number;
  floors: number;
  total_area_m2: number;
  country_currency: string;
}

export interface GenerationResult {
  project_id: string;
  rooms: RoomLayout[];
  geo_climate: GeoClimateData;
  mep_conflicts: MEPConflict[];
  compliance_issues: ComplianceIssue[];
  cost_estimate: CostEstimate;
  ifc_file_url: string;
  warnings: string[];
  insolation_score: number;
  site: SitePlan | null;
}

// The building placed on its plot (present only when a plot size was given).
// Offsets translate the plan's ground-floor min corner into the plot frame;
// clearances are the actual yard metres on each compass edge.
export interface SitePlan {
  plot_width_m: number;
  plot_depth_m: number;
  building_width_m: number;
  building_depth_m: number;
  offset_x: number;
  offset_y: number;
  street_side: "S" | "N" | "W" | "E";
  street_setback_m: number;
  neighbor_setback_m: number;
  clearances: Record<"S" | "N" | "W" | "E", number>;
  coverage_ratio: number;
  coverage_limit: number;
  seismic_zone: number;
  seismic_flag: boolean;
}

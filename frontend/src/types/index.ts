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

export interface RoomInput {
  room_type: RoomType;
  area_m2: number;
  name?: string;
}

export type BuildingShape = "rectangular" | "square" | "l_shape" | "u_shape" | "t_shape";

export interface BuildingParams {
  rooms: RoomInput[];
  country: CountryCode;
  region?: string;
  floors: number;
  plot_width_m?: number;
  plot_depth_m?: number;
  building_shape: BuildingShape;
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

export interface GenerationResult {
  project_id: string;
  rooms: RoomLayout[];
  geo_climate: GeoClimateData;
  mep_conflicts: MEPConflict[];
  compliance_issues: ComplianceIssue[];
  cost_estimate: CostEstimate;
  ifc_file_url: string;
  warnings: string[];
}

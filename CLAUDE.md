# ArchVision AI — Project Context

## What this is
Architectural sketch generator for RU/KZ/CIS market. User inputs household type → system produces 2D floor plan, MEP routing, cost estimate, PDF report, IFC export. Branch: `phase-2-production`.

## Stack
- **Frontend**: React + Vite + TypeScript + Zustand + Tailwind CSS v3 (NOT v4). **Brand = ArchVision "AV" mark, red accent `#E0261C`** (palette: red/black/white #F7F4EE/gray #8C8A85). The Tailwind `brand` token is the single accent source — recolor the whole app from `tailwind.config.js` `brand` scale; don't hardcode hex. Logo SVG (A+ruler / V+sun) lives in `App.tsx` header + `public/favicon.svg`.
- **Blueprint design language (2026-07-07, reviewer-driven)**: the UI inherits the drawing, not Dribbble. Fonts: Unbounded (display — wordmark only) + Golos Text (body) + JetBrains Mono (all data figures incl. the cost hero) — Space Grotesk was DROPPED because it has no Cyrillic (RU/KK headers silently fell back to system font); any replacement must ship Cyrillic. `tailwind.config.js` OVERRIDES the `slate` scale with a warm ink ramp (anchored on brand gray #8C8A85) and `surface.*` is warm paper — every `text-slate-*` class de-blues from that one table, same single-source trick as `brand`; don't reintroduce cool grays via inline hex. Utilities in `index.css`: `.paper-grid` (mm-grid canvas texture), `.stamp-frame`/`.stamp-cell` (drawing title block — the cost hero is a штамп with area/floors/ref cells), `.dim-rule` (45° dimension ticks on accordion dividers). Radii are deliberately tight (4–6px); no letter-spaced uppercase taglines.
- **Backend**: FastAPI + Python, reportlab, Groq API (llama-3.3-70b-versatile). NO Celery/Redis/Supabase/DB — file-based store in `generated/` (`{id}.json` + `{id}.ifc`), TTL-cleaned daily (`RESULT_TTL_DAYS`). Generation is synchronous in the request.
- **Groq key**: in `backend/.env` as `GROQ_API_KEY`
- **i18n**: 3 locales — `en`, `ru`, `kk` — all 3 must be updated together

## How to run locally
The backend runs in a venv at `backend/.venv` — the **global Python has NO pytest/uvicorn**, so always use the venv interpreter.
```
# Backend (Windows venv)
backend\.venv\Scripts\uvicorn main:app --reload --port 8000    # run from backend/

# Frontend
cd frontend && npm run dev
```
Tests (Windows):
- Backend: `backend\.venv\Scripts\python.exe -m pytest -q` (run from `backend/`)
- Frontend: `cd frontend && npx vitest run` then `npx tsc --noEmit`
- PowerShell cwd persists across tool calls; don't re-`cd` into a dir you're already in.

Visual/browser check: API path prefix is `/api/v1` (e.g. `POST /api/v1/generate-plan`). If the `chrome-devtools` MCP isn't loaded in-session, screenshot via `puppeteer-core` pointed at the system Chrome (`C:/Program Files/Google/Chrome/Application/chrome.exe`, forward slashes) — no Chromium download. Drive: click `.btn-primary` to generate, click the button containing "2D" to switch view. Generate needs BOTH servers up (uvicorn :8000 + `npm run dev` vite :3000).

## Key architecture decisions (do not re-derive)

### Layout engine (`backend/core/layout_engine.py`)
- **Central-hall layout + a REAL L (release 6, 2026-07-13)** — `building_shape` ∈ `rectangular|square|l_shape` (pydantic pattern; u/t still 422 — courtyard perimeter breaks cost/heating, they return only when they truly tile; contract pinned by `tests/test_shape_contract.py`). `_layout_l()`: wing A = central-hall bar (aspect 1.0, social+wet+garage, NO bedrooms), wing B = bedrooms row over a corridor cell that CONTINUES the hallway strip east of the seam (same y-band → circulation at the joint BY CONSTRUCTION — the old wing layouts stranded the hall in a corner and routed through a toilet). Wing-B depth targets bedroom aspect ~1.2 (`√(mean/1.2)`, clamp 2.4–4.2, snap flush to wing A's north edge if within 0.5 m) — sizing to the flush edge alone gave 5.8×2.4 pencil bedrooms and a 22 m snake that blew plot setbacks. Honest fallbacks (warning + rectangle): floors>1, <2 bedrooms, hall strip not reaching the seam. `engine.silhouette_m2` (None = rectangle) → `check_invariants(silhouette_m2=)` rule-1 denominator (an L judged against its bbox reads as a floor of gaps); LLMLayoutEngine exposes it as a property and routes l_shape past Groq. Site coverage counts Σ built rooms, not bbox (the notch is not chargeable); `walls.py` classifies exterior edges NEIGHBOUR-based (≥50% backed = partition) — the bbox test under-subtracted the notch walls. Cost/heating unchanged BY THEOREM: this L is staircase-monotone → true perimeter == bbox perimeter (`test_l_exterior_perimeter_equals_bbox_perimeter` pins it). Tests: `test_l_shape.py`, `test_l_consumers.py`.
- `USABLE_MIN_SIDE` dict — shared between layout engine and invariant checker (single source of truth for minimum room dimension per type)
- `_layout_central_hall()` — main layout function for all shapes
- `_assign_floor_doors()` + `_assign_windows()` — BFS door tree rooted at hallway; hallway gets exactly ONE entrance door on external wall
- **Garage band (DONE 2026-07-07)**: a garage is a footprint outlier — it gets its OWN full-width band at the back (max-y = north = cold-side thermal buffer), never inside the two shared bands (it used to inflate the min-side width raise until the wet band collapsed — the "kitchen ~1.3 m" shortfall, now fixed). Garage doors are planned in `_assign_garage_doors`, not grown by the BFS: 2.4 m vehicle gate with `DoorSpec.kind="gate"` on an external wall (corner-aligned, so the window fits beside it) + person-door into a mudroom-order neighbour (`_GARAGE_DOOR_PREF`: utility > kitchen > hallway > living; bath/toilet and bedrooms last — a bedroom parent would trip rule 4). `kind="gate"` renders as a straight panel (no swing arc) in BOTH `PlanView2D` `DoorSymbol` and the PDF; the PDF door loop also finally special-cases `kind="opening"` (jamb ticks, no arc — it used to draw a physically impossible 2-3 m swing leaf for open-plan openings). Tests: `backend/tests/test_pdf_plan_symbols.py`. Garage is pinned to the ground floor in `_distribute_floors` (cars do not climb stairs). `_assign_windows` skips a window that would land inside any same-wall door (the gate case). Tests: `backend/tests/test_garage_band.py`.
- **Wet stacking + clamped width raise (DONE 2026-07-08)** — the fix for the collapsed-bands defect (budget + narrow plot → every band flattened to 1.5–2.0 m, "гостиная-коридор"). Root cause: the min-side width raise for a 1.2 m² toilet pushed house width to ~15.7 m unbounded. Now: (1) rows are built from CELLS — a cell is one room or a stacked column of small wet rooms (`_STACKABLE` = bath/toilet/utility, `_stack_cells`); the stack keeps one plumbing wall (rule 5/MEP bonus) and the largest member faces the hallway (toilet tucks behind the bathroom; BFS pass 2 doors it through the bath). (2) `_donated_widths` is cell-based and symmetric — the same helper distributes depths INSIDE a column. (3) A still-needed width raise is CLAMPED to the habitable bands' depth caps (`ceiling`) — saving a toilet must never crush the bedrooms; the residue ships as an honest INV-9 red, never green. (4) The garage band has a physical depth floor (`min_depth` in `_emit_row`): `USABLE_MIN_SIDE[GARAGE]=3.0` (gate 2.4 + car ~1.8–2.0 — a 2.4 m garage cannot be entered); at tight widths the garage honestly GROWS past its requested area (cost uses w×d so it's priced). Stacking activates ONLY when plain donation fails — passing programs keep their geometry. Tests: `backend/tests/test_wet_stacking.py`. Closed mode can still be genuinely infeasible (kitchen pinned to the wet band) — it flags red, by design.
- **Hallway real figure (DONE 2026-07-08)** — the full-width hall band (1.3 m depth floor) ballooned to 2.2× its request on wide houses ("15.6 m² прихожая", printed at the whole building width). When it overshoots 1.6×, the strip's W end goes to the smallest toilet/utility that fits (guest WC by the entrance) — W because the south band's wet cells sort first (`ROOM_ORDER`), so the pulled toilet lands on the bathroom's riser wall. Guarded three ways: the donor band must keep its deepest-min depth AND clear its cell minimums without the pulled room (pulling the toilet out of the closed-mode WET band starved the kitchen to 1.5 m — that's why the feasibility check exists), and the emitted floor re-verifies the wet cluster (`_wet_connected`) with a fallback to the legacy full band. Test: `test_hallway_prints_its_real_figure_not_the_house_width`.
- **UTILITY is a wet zone in the LAYOUT too (2026-07-08)** — layout `WET_ZONES` now matches `mep.pipe_router.WET_ZONES`. Banded with the bedrooms, the 4 m² хозблок became a 0.65 m sliver in the deep dry band → `_row_ok` rejected central-hall → the FAMILY PRESET (the storefront!) shipped tiled with rule-4/9 reds. All 4 presets ± garage at defaults are pinned clean by `tests/test_presets_clean.py` (mirrors `presets.ts`); family with 3–4 kids on ONE floor stays honestly red — that's "нужен второй этаж" physics, deliberately not pinned.
- `LLMLayoutEngine` in `llm_layout_engine.py` wraps `LayoutEngine` with Groq agentic loop (5 iterations → fallback to rule-based)

### Invariants (`backend/core/plan_invariants.py`)
9 rules checked deterministically after every generation. **Wired into the route 2026-07-08**: `check_invariants()` used to run ONLY in tests — a plan violating rule 9 (1.8 m "living room") shipped with a green "all rules passed" badge. `routes.py` now mirrors every violation into `compliance_issues` as an `INV-{rule}-{CODE}` ERROR (message text intact, so UI «Нормы» and the PDF print WHAT is broken), running after auto-orient so it judges final geometry. Regression anchor: `backend/tests/test_invariants_in_prod.py` (the real bug-report scenario: budget + 12 m plot + garage + 2 bedrooms). The rules:
1. No overlaps + coverage ≥ 90% of bbox
2. Areas ≥ 90% of requested
3. Every room has a door
4. No transit through bedroom to reach circulation
5. Wet zones share one riser per floor
6. Entrance via hallway buffer (`EXT_DOOR_OK` exempts the garage — a vehicle gate is not the pedestrian entrance, the garage is its own unheated buffer)
7. Wet-over-wet across floors
8. Mandatory: kitchen + bathroom/toilet
9. Min usable dimension (uses `USABLE_MIN_SIDE`)

### Honest naming (2026-07-08) — don't regress the copy
- «Нормы» renamed to «Предварительная проверка» everywhere (UI accordion, PDF section): we check areas+geometry, NOT building codes. Clean state is a TRAFFIC LIGHT: green «Площади и геометрия проверены» + amber «Нормы (СНиП/СП) — проверка у специалиста». Keys: `results.precheckPassed`/`codesNeedExpert` (old `allRulesPassed` deleted).
- MEP clean state is a status badge (icon + title + scope subtitle `results.mepCheckedScope`): the subtitle names what WAS checked («стояк и разводка воды (черновик)») — a bare "no clashes" implies disciplines we don't do.
- Footer/PDF disclaimer: «Черновая планировка и ориентировочная смета — чтобы прийти к архитектору подготовленным. Не проектная документация.»
- Repo is publish-ready: README (hero `docs/hero.png`, what-it-does-NOT section, roadmap with site-placement first), MIT LICENSE. **3D RESTORED (release 8, 2026-07-13)**: VIEW_MODES has both entries again; the scene is warm-paper blueprint (bg `#f4f0e6`, flat high-ambient «cardboard model» light — hard shadows ate the pastels), walls use the SAME `ROOM_FILL_2D` pastels as the 2D plan (`ROOM_COLORS` dark-era palette DELETED), labels via `roomDisplayName` + NET area (the flip's primary), door kinds honoured (opening = translucent void, gate = light panel). CameraRig effect needs `camera` in deps — `makeDefault` swaps the camera after the rig positions the old one and the house opens half out of frame (mount race). Headless verify: SwiftShader needs `--use-angle=swiftshader --enable-unsafe-swiftshader` + ~7 s first-frame settle.

### Three-category filter (never mix these up)
- **Invariants** — always enforced, no UI toggle
- **Smart defaults** — always on, no UI (wet zone grouping, min dims, floor stacking)
- **Preferences** — shown in UI (household preset, openness, spaciousness, facing/daylight; future: style, material)

### Openness (open ↔ closed social zone) — a preference
- `BuildingParams.openness` ∈ `closed | mixed | open` (default `closed` → original behavior, all legacy tests unchanged). Frontend type `Openness`; UI is a 3-way picker in `ParameterForm` after the shape selector.
- **closed**: every room walled; kitchen sits in the wet/south band; full central hallway; entrance via hallway.
- **mixed**: social band (living+kitchen) adjacent in the north band, joined by ONE wide cased opening; hallway kept for bedrooms/bath; entrance via hallway.
- **open**: same merged social zone; the hallway is KEPT as an entry buffer (тамбур) but **opened up** to the social volume via a wide opening (`_open_social_zone` opens kitchen↔living AND hallway↔living). Entry buffer is an invariant in EVERY mode (cold-climate тамбур) — `open` just has no walled corridor.
- The merge is represented as a wide opening, NOT a new room: `DoorSpec.kind="opening"` (width 1.6–3.0 m, no swing leaf) placed on BOTH sides of the shared wall (so neither room is left doorless — rule 3). `_open_pair()` is the reusable helper. Kitchen stays a real room (invariant 8, MEP, cost, IFC, localized name all keep working). `PlanView2D` `DoorSymbol` renders `kind="opening"` as an erased wall + jamb ticks.
- Openness is **openness-aware in two places**: layout banding (`_layout_central_hall` social vs wet bands; `_open_social_zone()` adds the openings) and `check_invariants(rooms, openness=…)` — rule 5 excludes the kitchen from the wet riser cluster. Rule 6 (entrance buffer) now applies in ALL modes (the hallway exists everywhere). A bedroom is never a door-tree parent (`PRIVATE_ZONES`), so you never route through a bedroom.
- **open/mixed always use the rule engine** (`LLMLayoutEngine` routes them past Groq) — the LLM prompt only knows the closed central-hall plan, and the geometry must be deterministic. Tests: `backend/tests/test_openness.py`.

### Budget ↔ spacious (`spaciousness`) — a preference
- `BuildingParams.spaciousness` ∈ [0,1] (default 0.5 = neutral, unchanged). ONE intuitive slider, implemented as a single lever: `scale_room_areas()` multiplies every room area by `area_factor(s)` (0.80–1.20). Smaller areas → smaller footprint → less perimeter (less exterior wall, insulation, heat loss) AND cheaper; bigger → pricier. Applied in BOTH `LayoutEngine.generate()` and the LLM path. Cost falls out of the layout automatically.
- No separate "compactness" lever: an explicit aspect/squareness knob fought the engine's min-side enforcement (min-side raises width back up), so it was dropped — area scaling already delivers the compactness/heat-loss benefit. At the budget extreme the wet band can dip below the kitchen min-side; that is the engine's documented "honest shortfall", not a bug.
- Width-sizing in `_layout_central_hall` now applies all depth caps first, THEN all min-side raises (min-side is the documented winner) — fixes an ordering bug area-shrink exposed. Tests: `backend/tests/test_spaciousness.py`.

### Daylight / orientation — built in LAYERS (sensor → actuator)
The room solver stays **blind to sun** (it places by function: wet/social/private bands). Orientation is layered on top, never inside the solver — placing "living→south, bedrooms→east" by moving rooms would break the wet riser, openness merge, and no-transit rules.
- **Layer 1 — SENSOR (DONE).** `BuildingParams.facing` ∈ N/NE/E/SE/S/SW/W/NW (bearing the plan's "N" wall points to; default "N"). `backend/core/insolation.py`: `annotate(rooms, facing)` sets `RoomLayout.sun` = good/ok/poor/"" (living/kitchen want south, bedroom wants east; bath/toilet/hallway/utility/garage unrated); `score(rooms, facing)` → 0..100 with the living room weighted ×3. Route annotates rooms + sets `GenerationResult.insolation_score`. Tests: `backend/tests/test_insolation.py`. Frontend shows a sun dot per room + the score (read-only).
- **Layer 2 — ACTUATOR (DONE).** `BuildingParams.auto_orient` (default false). `backend/core/orientation.py`: `best_turns()` tries 4 quarter-turns, picks the one maximizing `score()` (living weighted ×3 → living-south wins) with plot-fit + a margin so it never rotates gratuitously; `rotate_layout()` applies a rigid CW turn carrying doors/windows along (wall+position transform — NOT reassignment, so prediction==outcome). Route runs it before the sensor when `auto_orient`. Two convention gotchas baked into tests: in this engine `"S"`=min-y wall, `"N"`=max-y; a CW geometry turn shifts a wall's compass bearing by **−90°** (so `shift_facing` subtracts). Tests: `backend/tests/test_orientation.py`.
- **Sun badge ≠ MEP dot:** the 2D sun rating is a rayed SUN glyph (`SUN_RAYS` in `PlanView2D`), not a plain disc, with its own legend row (`viewer.daylight`) — a plain amber disc collided with the medium-MEP-conflict marker.
- **Headline quality score** (`ResultsPanel.planQualityScore`) now folds in daylight: `round(0.7·issueScore + 0.3·insolation_score)`, so a clean-but-dim plan no longer reads the same "100" as a sunny one.

### Cost-Δ variants (roadmap C, DONE 2026-07-12) — the decision table, not a gallery
- `core/variants.py build_variants()` — 3 FIXED settings (compact 0.0 / balanced 0.5 / roomy 1.0), **rule engine only** (never Groq: the table the user acts on must be reproducible), computed inside `generate-plan` → `GenerationResult.variants` (default `[]` keeps pre-variants `{id}.json` loadable), **sorted by cost ascending**.
- Row = footprint Σw×d, cost, Δ vs cheapest, `delta_driver` ∈ concrete|walls (from `cost.breakdown`: concrete+rebar vs brick+insulation; labor excluded — fixed fraction, can't win), `red_flags` = invariant ERRORs + site breaches on the re-tiled plan (mirror-tested against the actual checkers).
- FE: accordion «Варианты по бюджету» under Cost breakdown; collapsed badge = saving vs the canvas plan; «применить» ONLY sets the spaciousness slider (no auto-generate — rate limit) + toast; row matching current slider gets a «текущий» chip; honesty note names the deterministic engine. Tests: `backend/tests/test_variants.py`.

### Second-floor hint (DONE 2026-07-13) — data-driven, never presumptive
- `frontend/src/components/secondFloorHint.ts needsSecondFloorHint(issues, floors)`: amber hint + «2 этажа» button in `ComplianceCard` when floors==1 AND the checkers actually flagged a squeeze (`/^INV-(2|9)-/` ERROR). Button only sets `floors: 2` + toast (same no-auto-generate pattern as variants apply). Hint hides reactively the moment floors flips — the stale red issues stay until regeneration, by design. Closes the family-3–4-kids-on-one-floor storyline: red → one click → «Хорошо». i18n ×3, unit-tested.

### Household presets (`frontend/src/presets.ts`)
- `couple` / `family` / `single` / `rental` → `buildPresetRooms(preset, kids?, garage?)`
- Family preset: `kids` param (1–4) controls bedroom count
- **Garage = preset modifier** (like `kids`, but valid for EVERY preset): a switch in `ParameterForm` appends a one-car garage (`GARAGE_AREA_M2 = 22`) to the active program without dropping to "custom". Persisted in `archvision_preset_v1` next to `familyKids`. On "custom" the toggle adds/removes the garage room in place (hand-edits survive; a hand-added garage is never duplicated). The switch reflects the ACTUAL program (`rooms.some(garage)`), not just the stored flag.
- Manual edits set `preset: "custom"` in store (in-memory only)
- Only an explicitly chosen preset is persisted (`localStorage` key `archvision_preset_v1`); `"custom"` is NOT written on every keystroke. On load `deriveActivePreset()` re-derives `"custom"` when stored rooms no longer match the stored preset's program — this keeps room-edit persistence to one debounced write. `DEFAULT_PARAMS` equals the `couple` program so a fresh load resolves to `couple`.

### Cost model (`backend/core/cost_estimator.py`)
- Strip foundation (not full-area raft) + slabs
- Interior walls counted ONCE via `(Σ perimeters - exterior) / 2`
- Target: ~0.7 m³/m² concrete (was ~1.6 before fix)

### Heating draft (release 3, DONE 2026-07-13) — `backend/core/heat_calculator.py`
- `estimate_heating(rooms, geo)` — U-value envelope method over the REAL geo-driven wall/insulation thicknesses; window fraction = `1 − EXT_SOLID_FRAC` (imports the cost model's constant — single source); vent 0.35 ACH; garage EXCLUDED (unheated buffer, `heated_area_m2` proves it in tests). `GeoClimateData.design_temp_c` is DERIVED from AFI (`−(5+0.45·√AFI)`, fit vs СП 131 anchors, ±5 °C draft — boiler margin ×1.25 absorbs it); None on old stored results, and `GenerationResult.heating` defaults None too.
- **Heating cost lives INSIDE `CostEstimator.estimate()`** (lazy import to dodge the import cycle; added AFTER labor — installed price, don't double-multiply) → hero, variants, PDF and the breakdown line stay consistent automatically. UI: «Отопление (черновик)» accordion + honest amber note (не СП 50). Tests: `backend/tests/test_heating.py`.

### T-shape + true perimeter (release 11, DONE 2026-07-14)
- `_layout_t`: bedrooms wing WEST + garage/utility wing EAST over corridor continuations of the strip; the stem (living/wet bar) faces the street between two entrance nooks. Requires ≥2 bedrooms AND garage/utility AND the strip spanning the FULL bar (a filler WC at the W end would cut the west corridor off) — else warning + honest degradation chain **t → l → rectangle** in `_layout_floor`; floors>1 → the two-storey Г takes over. Wing A is SHIFTED east by the west wing's width (safe: openings assigned after tiling). `u_shape` stays 422 — composer-only blocker now.
- **Cost/heating bill the TRUE exterior**: `_floor_walls` exterior = exposed-edge sum (`_exposed`, eps 5e-3 for 3-dp rounding) — rect/L equal their bbox by monotonicity (pinned), the stepped T runs LONGER (wing tops break y-monotonicity; the flush-snap only fires within 0.5 m), a future courtyard U is priced too. The bbox shortcut silently under-billed every re-entrant wall.
- Entrance root: `_assign_floor_doors` prefers a hallway WITH an exterior wall — in the T the central strip is boxed in by corridors on both ends, so the entrance lands on a wing corridor's street-nook face. Tests: `tests/test_t_shape.py`.

### Multi-floor L (release 10, DONE 2026-07-14) — the two-storey Г-дом
- `_layout_l` branches on floors: 1 floor = bedroom wing (release 6, unchanged); ≥2 floors, floor 1 = **garage(+utility) wing** over the corridor continuation (person-door via the corridor buffer → rule 10 has NOTHING to say; gate faces the notch = driveway), needs garage OR utility on the ground else warning+rectangle; floor ≥2 = `_layout_central_hall(max_width=self._l_w1)` — upper floors PINNED to wing A's width (overhang is structural fiction; raises past the cap ship as honest shortfalls). `_l_w1` reset in `_tile` (two net-target passes).
- `silhouette_m2` is now `dict[floor, m²] | float | None`: dict = per-floor outlines (L ground, bbox-judged upper floors); float = legacy single-floor L; invariants accept all three.
- **Latent bug killed**: UTILITY was missing from `GROUND_FLOOR_ZONES` — sent upstairs, the lone tiny wet band capped the WHOLE upper floor's width to ~2.8 m (1.46×15.39 pencil bedrooms) for ANY 2-floor + utility program, not just L. Utility is plumbing; it lives on the ground. Tests: `tests/test_l_two_floors.py`.

### Rule 9 on clear dimensions (release 9, DONE 2026-07-14) — the last axis holdout
- Rule 9 judges NET dims when annotated (axis fallback; message says «clear»). Engine sizing pads: `self._wall_pad = ext_t + INTERIOR_WALL_T/2`; `_need(cell, idx, n, pads)` is **position-aware for widths** (row END cells = full pad, middle = 2 half-partitions — uniform full pad made donation fail by centimetres) and **band-aware for depths** (`pad_s = INTERIOR_WALL_T if buffer_band else _wall_pad` — the middle band touches partitions on both edges; the full pad capped house width below what bedrooms needed: the rental+garage 1.5 cm near-miss). Cells MUST be in spatial W→E order for corner indices to mean corners — `_row_cells()` is the single sorted constructor (`_order_key` hoisted to module scope).
- Garage is GROSSED like everything else (22 m² = parking metres in the clear; min-depth 3.0+pad is a separate physical floor). Tambour area follows physics `t = need·S/(w−need)` instead of a fixed 1.5 sliver. The hall-strip filler's `wt` includes a net-delivery term — the draft pass measured the WC's losses at its old position, so the measured gross-up doesn't cover the move into the strip corner; the 0.35·width gate then honestly rejects pulls that got too fat (fallback = legacy full band). `test_presets_clean` now annotates net BEFORE checking — pinned to the production path. Tests: `tests/test_rule9_net.py`.

### Net-target flip (release 7, DONE 2026-07-13) — «12 м²» = 12 полезных
- `LayoutEngine.generate()` is TWO fixed passes: `_tile` draft → `annotate_net_dims` → per-room gross factor `axis/net` (clamp 1.0–1.5; GARAGE + HALLWAY exempt — physics/real-figure) → retile → **restore the USER's request into `area_m2`** (match by type+grossed-area). LLM path: prompt targets ×`NET_GROSSUP_EST`(1.15) + same restore. Deterministic; warnings deduped (fallback warnings would fire twice).
- **Rule 2 judges net_area when annotated** (axis fallback keeps old results/callers on legacy); HALLWAY exempt from rule 2 (its area_m2 may BE the axis figure — corridor B, tambour). Variants annotate net before counting flags. **Rule 9 intentionally still AXIS** — judging net needs corner-aware band sizing (thick-wall corner rooms must be GROWN, not flag-flooded) = next roadmap step, documented in README.
- **Display split**: room-level figures = NET everywhere (canvas label, hover primary, PDF plan label + table column, DXF экспликация); building-level = AXIS (штамп, floor totals, /projects, site coverage, cost basis — the real outer envelope). Hover secondary = «в осях N m² (со стенами)» (`viewer.axisArea`; `viewer.netArea` deleted).
- Two prior tests recalibrated honestly: budget-hall bound 2.0→2.4× (the whole house is ~10% wider now — the bound guards the 3.3× absurdity, not honest growth); L-corridor finder = easternmost hallway (the overshoot filler can pull a WC into the wing-A strip, shifting its x). Tests: `tests/test_net_targets.py`.

### Net (usable) areas (release 5, DONE 2026-07-13) — `backend/core/walls.py`
- `annotate_net_dims(rooms, geo)` (route step 3c, AFTER auto-orient): exterior wall grows INWARD from the axis at full `wall_thickness_mm` (bbox stays the real outer footprint — site/cost basis unchanged; insulation is outside, not subtracted), interior partitions ½·`INTERIOR_WALL_T` per side; an edge on the floor bbox = exterior. Sets `RoomLayout.net_width/net_depth/net_area` (None on old stored results — every consumer must handle it).
- **Axis figure stays the PRIMARY single definition everywhere**; net is the second, explicitly labeled figure: hover card (`viewer.netArea`), PDF room table «Полезная» column (— for None). Do NOT flip the primary piecemeal — flipping means the whole pass (engine sizes to net targets + INV-9 judges net), roadmap #2. Tests: `tests/test_net_areas.py`.

### DXF export (release 4, DONE 2026-07-13) — `backend/core/dxf_generator.py`
- `GET /api/v1/dxf/{id}?lang=` → `generate_dxf(result, lang)`: R2010, **mm units** (CIS CAD convention — engine metres ×1000), layers WALLS(7)/DOORS(1)/WINDOWS(5)/LABELS(8), floors side by side in one modelspace with «Этаж N» captions, room labels via the PDF's `_room_label` (single localization source). Openings = one LINE on the host wall per spec (sketch handoff, no swing arcs). Dep: `ezdxf==1.4.4` (MIT) in both requirements files. Tests parse the emitted file BACK with ezdxf (`tests/test_dxf.py`); visual check = ezdxf drawing add-on → matplotlib PNG (matplotlib is dev-venv only, NOT in requirements).

### PDF (`backend/core/pdf_generator.py`)
- Embeds actual 2D floor plan drawing (one per floor) via reportlab vector graphics
- `_floor_plan_drawing(rooms, avail_w, caption, lang)` → `Drawing` (lang threaded for localized labels)
- 3D is NOT in PDF — "на 3д забиваем"

### Localized room names (2D plan + PDF)
- Layout engine stores `RoomLayout.name = custom_name or room_type.title()` (English default, no index).
- Display heuristic (single source of truth, mirrored FE/BE): if `name` equals the English-title default of `room_type` → it's generated → localize via the shared `roomTypes.*` labels; else it's the user's custom name → show verbatim.
- Frontend: `roomDisplayName(room, t)` in `components/roomName.ts`, used by `PlanView2D`'s `RoomLabel`.
- Backend: `_room_label(room, lang)` + `_ROOM_LABELS` in `pdf_generator.py` (labels match FE i18n `roomTypes.*`).
- 3D viewer (`ThreeViewer.tsx`) intentionally NOT localized — out of scope per "touch 3D only if asked".

### MEP draft v1 — the moat (`backend/mep/` + 2D visual layer)
An honest sketch-level plumbing DRAFT over the plan, NOT a buildable spec (drains/slopes/pressure are an engineer's job + legal liability — out of scope on purpose).
- Wet points = kitchen, bathroom, toilet, **and laundry (`utility`)** — `pipe_router.WET_ZONES`.
- `pipe_router.py`: `riser_xy()` = centre of largest wet room on lowest wet floor; vertical riser stack connects wet floors.
- `clash_detector.py`: flags `pipe_through_room` (habitable only) PLUS two honest advisories from `_costly_zones()`: `far_from_riser` (MEDIUM, wet room >6 m from riser → its own long branch; fires for open/mixed kitchens) and `wet_over_dry` (HIGH, upper-floor wet room stacked over a living space). New conflict types just need a `mepHints.<type>` i18n key.
- **2D visual layer** (`PlanView2D`, gated by `showMEP`): cyan wet-point drops (`WaterDrop`), a riser ring glyph, and dashed "approximate branch" lines wet→riser. Everything runs along the TOP of the wet band (just inside the back wall, `fy(r.y+r.depth)+0.45`) so it never overlaps the centred room labels — do NOT move it back to room centres (the drops landed on the area text). The riser is computed FRONTEND-side via `computeRiser()` — a deliberate mirror of `riser_xy()` (no extra API field). `mep_riser` was intentionally NOT added to the result.
- Honesty guard: `ResultsPanel` MEP tab shows a `results.mepDraftNote` disclaimer ("draft for engineer coordination") in both the clean and flagged states; legend row `viewer.mepDraft`. Tests: `backend/tests/test_mep_draft.py`.

## File map (critical files only)
```
backend/
  core/
    layout_engine.py      ← central-hall layout, USABLE_MIN_SIDE, BFS doors
    llm_layout_engine.py  ← Groq agentic loop + fallback
    plan_invariants.py    ← 9 invariant rules
    plan_validator.py     ← geometry checker (overlaps, gaps, bounds)
    cost_estimator.py     ← strip foundation cost model
    pdf_generator.py      ← 2D floor plan drawing embedded in PDF
  mep/
    pipe_router.py        ← riser placement + vertical stack
    clash_detector.py     ← HABITABLE-only conflict detection
  api/routes.py           ← uses LLMLayoutEngine (not LayoutEngine directly)
  tests/                  ← pytest; run with `pytest`

frontend/src/
  presets.ts              ← buildPresetRooms(), FAMILY_KIDS_* + GARAGE_AREA_M2 constants
  store/useStore.ts       ← Zustand; preset + familyKids + garage state; saveParams debounced 300ms
  components/
    ParameterForm.tsx     ← preset picker (primary), rooms collapsible (advanced)
    PlanView2D.tsx        ← 2D canvas; MEP layer, sun badges, Finch-style hover metrics card
    ResultsPanel.tsx      ← cost-hero + collapsible accordions + status badges (Stripe/Figma); undo button
  i18n/locales/
    en.ts / ru.ts / kk.ts ← always update all 3
```

### UI / interaction patterns (3 visible reviewer references: Finch3D, Stripe, Figma)
- **Right panel** (`ResultsPanel`): cost is an always-visible HERO (big, ink-coloured — color is reserved for status); everything else (`CostBreakdown`, `GeoCard`, `ComplianceCard`) is a `defaultOpen={false}` `Accordion` with a right-side `StatusBadge` (green ✓ / red count) so a collapsed section still reads. Don't dump it all open again — that was the "свалка" the reviewer flagged.
- **Hover metrics** (`PlanView2D`): hovering a room shows a Finch-style floating card (name + w×d area + dims + daylight) via `onHover`/`HoverInfo`; the riser/conflict overlays stay `pointerEvents:none` so the room rect receives the hover. On-plan labels are therefore minimal (name + area; dims only when `selected`).
- **Undo / version history** (`useStore`): `setResult` pushes the outgoing plan onto `history[]` (cap 8, newest first); `undoResult()` pops it. The panel header shows `↶ {history.length}` when `history.length > 0`. No redo (stepping back discards the forward plan).
- **Conflict legend** rows render only when `result.mep_conflicts.length > 0` (no phantom legend).

## MVP production hardening (DONE 2026-07-06) — key decisions
- **No accounts**: anonymous `X-Device-Token` (uuid in `localStorage archvision_device_v1`, minted in `client.ts deviceToken()`, sent on every request via axios interceptor). Backend stamps it as `_owner` INSIDE the stored `{id}.json` (pydantic ignores extra on load → `/projects/{id}` never echoes it). `/projects` lists only the caller's token; empty without one.
- **NEVER re-add a static mount over `IFC_OUTPUT_DIR`** — it serves raw `{id}.json` incl. `_owner` (share recipient could steal the owner token and list their history). Files go out only via validated routes; guarded by `test_raw_store_not_exposed`.
- **Share/refresh**: hash routing `#/p/{id}` in `App.tsx` (module-level `shareLoadInFlight` guards StrictMode double-mount); generate sets the hash. History dropdown = `HistoryMenu.tsx`.
- **Rate limit**: in-proc sliding window (`core/ratelimit.py`), keyed by client IP, 5/min + 30/day (env). 429 pre-generation; rejected probes not recorded. Needs `--proxy-headers` behind nginx (prod Dockerfile has it). LLM: 30 s per Groq call + 90 s wall budget (`LLM_TIME_BUDGET_S`) → rule-engine fallback. Persist failure = honest 500, not fake success.
- **Prod deploy**: `docker compose -f docker-compose.prod.yml up --build -d` — nginx (SPA + /api proxy) + non-root uvicorn; own volume `ifc_files_prod`. Verified end-to-end incl. restart persistence.
- **Mobile (<md)**: form = drawer (hamburger), results = 60vh bottom sheet, `PlanView2D` container shrinks up (desktop: right) via `useIsDesktop()`; pinch-zoom = 2-pointer in PlanView2D. ThreeViewer still untouched.

## Self-rules additions (2026-07-06)
- `npm ci` in Docker can fail on a lock npm 11 wrote (nested vite7/esbuild entries) while local `npm ci --dry-run` passes — builder pins `npm@^11`; if lock desyncs again, delete + full `npm install` regen.
- A dir COPY'd into a Docker image from this OneDrive-synced repo can carry READ-ONLY mode (555) → named volume inherits it on first use → EACCES for non-root. `chmod 775` explicitly in the Dockerfile; `.dockerignore` keeps `generated/`, `.venv/` and **`.env` (real key!)** out of images/contexts.
- uvicorn `--reload` on this machine has silently served STALE code — after backend edits, verify a changed endpoint responds new-style (e.g. tokenless `/projects` → `[]`), else restart the process.
- pydantic-settings v2 with `env_file` FORBIDS unknown keys by default — removing a setting while operators' `.env` still has it crashes startup; `extra="ignore"` is set in `config.py`, keep it.

## Known issues / current work (as of 2026-07-08)
- Habitable min side is **2.4 m** (`USABLE_MIN_SIDE`; garage **3.0** — physical, see Layout engine). The shared-width coupling got its rethink 2026-07-08 (wet stacking + the raise clamped to habitable depth caps), so raising living/bedroom to 2.6–2.7 is now a TUNING question, not an architecture blocker — untested, verify against the wet band before flipping. The LLM path is gated by the SAME table via `plan_validator.MIN_SIDE`, so LLM "pencil" rooms (2.0–2.3 m) are rejected → rule-engine fallback.
- ~~Garage-heavy programs hit an honest wet-band shortfall (kitchen ~1.3 m)~~ — FIXED 2026-07-07 by the garage band; ~~budget+narrow-plot programs collapsed EVERY band to 1.5–2.0 m and still showed green~~ — FIXED 2026-07-08 (wet stacking + clamp + invariants wired into the route). Genuinely infeasible programs (e.g. closed mode pinning the kitchen to the wet band on a tight plot) now ship with red INV-9 issues instead of silence — that's the designed behaviour, not a bug.
- Walls are NOT subtracted from areas anywhere (axis-line geometry): the "D" task — wall thickness offsets across layout/PDF/cost/IFC — is deliberately deferred; all result surfaces show one consistent w×d figure meanwhile (incl. `/projects` listing since 2026-07-08).
- Conflict dots on 2D plan have hover tooltips (severity + description + localized `mepHints.*` hint) via the shared floating `hover-card`; hit area is a transparent r=0.34 circle with `cursor: help` (DONE 2026-07-03)

### Displayed area = ACTUAL footprint (single definition)
- Room area shown on the 2D canvas AND in the PDF (per-room + floor total) is `width × depth` (the real tiled footprint), NOT the requested `area_m2`. They diverged before (e.g. the full-width hallway: requested 4.8 m² but actual 8.4×1.3 = 10.9 m²), which made canvas (Σ area_m2) ≠ PDF/gabarit (Σ w×d) and the PDF internally inconsistent (header vs room table). `area_m2` stays the requested value (used by invariant rule 2 only).
- Cost display is locale-driven: local currency primary (KZ→KZT, RU→RUB), USD secondary; US shows USD only (`ResultsPanel` cost card).

## Coding rules (enforced by user)
- Karpathy method: diagnose → write failing test → fix
- No comments unless WHY is non-obvious
- No backwards-compat shims for removed code
- Tailwind v3 only (no v4 syntax)
- Touch 3D viewer (`ThreeViewer.tsx`) only if explicitly asked (asked & restored in release 8 — the rule still applies to incidental churn)
- Never mock the database / external services in tests that are meant to catch real integration bugs
- RUB primary currency for RU/KZ, USD secondary

## Self-rules — mistakes already made here, do NOT repeat them
These cost real cycles. Read before touching shell, geometry, or adding UI/metrics.

### Windows / shell
- git-bash `/tmp` ≠ Windows-Python `/tmp` (the latter is `C:\tmp`). When a bash command (e.g. `curl -o`) writes a file a Windows exe (`python.exe`) then reads, use a RELATIVE path in a shared cwd or a `C:/...` path — never `/tmp`. (Lost 2 cycles to "FileNotFound".)
- In bash heredocs, Windows paths with `\` get mangled (`C:\\Program Files` → backslashes stripped → broken path). Use FORWARD slashes for Windows paths in any script written via heredoc — Node and Python accept them.
- Foreground `sleep` is blocked; never chain `sleep N && cmd`. Use `run_in_background` or Monitor.
- PowerShell cwd persists between tool calls — re-`cd` into the dir you're already in errors. Check first.
- Killing a background uvicorn by its port's `OwningProcess` can leave a multiprocessing `spawn_main` CHILD alive holding the socket — the TCP table then shows a DEAD pid as owner ("port free" lies, the ghost serves STALE code). Sweep via `Get-CimInstance Win32_Process` filtering `CommandLine -match "spawn_main|uvicorn"`; verify the running server's code version by probing a route that only the new code has.

### Browser-driving the app (puppeteer verification)
- The dev Groq key is free-tier THROTTLED: closed-mode generation hits 429-retry loops and takes ~90–150 s before the rule-engine fallback returns. Browser waits must exceed `LLM_TIME_BUDGET_S`; a 45–90 s wait times out and looks like a frontend bug.
- Don't gate a "regenerated" wait on toasts or on the hint disappearing — toasts are transient and the second-floor hint hides REACTIVELY when params change. Wait on the штамп cell text (e.g. «ЭТАЖЕЙ 2») — it only changes when the new result actually lands.

### MCP / sub-agents
- `claude mcp add` mid-session does NOT load the tools into the running session — they appear only after a reload. Don't try to call them the same turn; tell the user to reload, or fall back (we used `puppeteer-core` → system Chrome for screenshots).
- Sonnet sub-agents here cannot run the terminal (shell denied) and may crash mid-task. ALWAYS re-run tsc/pytest/vitest yourself afterwards; treat a sub-agent's "done" as unverified.

### Layout-engine geometry (bit me hard during auto-rotate)
- Wall labels are FLIPPED vs intuition: `"S"` = min-y edge, `"N"` = max-y edge; `"W"` = min-x, `"E"` = max-x (the renderer flips Y so larger y = up = north). Check this before ANY wall math.
- A rigid transform (rotation) must CARRY existing openings (wall+position) along — never clear-and-reassign, or the score prediction ≠ the actual outcome.
- A clockwise quarter-turn shifts a wall's compass bearing by −90° (not +90°). Whenever a transform has a sign/direction, VERIFY prediction == actual empirically (transform a copy, compare) before trusting the formula.
- A wide opening between two merged rooms must be placed on BOTH rooms' shared wall, else the fully-merged room is left "doorless" and fails invariant rule 3.
- Don't add speculative levers: the aspect/"compactness" knob fought the min-side width enforcement and broke invariants; the area lever already delivered the effect. Verify any new lever against `check_invariants` first.

### Feature wiring
- New `BuildingParams` field → its default MUST reproduce current behavior so legacy tests pass (`openness="closed"`, `spaciousness=0.5`, `facing="N"`, `auto_orient=false`).
- New visual indicator → (a) must NOT reuse an existing legend color (an amber sun dot collided with the medium-MEP-conflict marker), and (b) MUST get its own legend row.
- New quality/health metric (e.g. insolation) → wire it into the headline aggregate score, or the score silently lies ("Хорошо 100" with 78/100 daylight).
- Three engines see params: `LayoutEngine.generate()`, the LLM path in `LLMLayoutEngine.generate()`, AND the route post-steps. A param that changes geometry usually must be handled in all relevant ones (spaciousness needed both engines).

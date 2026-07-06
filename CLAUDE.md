# ArchVision AI — Project Context

## What this is
Architectural sketch generator for RU/KZ/CIS market. User inputs household type → system produces 2D floor plan, MEP routing, cost estimate, PDF report, IFC export. Branch: `phase-2-production`.

## Stack
- **Frontend**: React + Vite + TypeScript + Zustand + Tailwind CSS v3 (NOT v4). **Brand = ArchVision "AV" mark, red accent `#E0261C`** (palette: red/black/white #F7F4EE/gray #8C8A85). The Tailwind `brand` token is the single accent source — recolor the whole app from `tailwind.config.js` `brand` scale; don't hardcode hex. Fonts: Space Grotesk (display) + Inter. Logo SVG (A+ruler / V+sun) lives in `App.tsx` header + `public/favicon.svg`.
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
- **Central-hall layout only** — full-width hallway band splits rooms north/south. L/U/T silhouettes are plot shapes, NOT layout types.
- `USABLE_MIN_SIDE` dict — shared between layout engine and invariant checker (single source of truth for minimum room dimension per type)
- `_layout_central_hall()` — main layout function for all shapes
- `_assign_floor_doors()` + `_assign_windows()` — BFS door tree rooted at hallway; hallway gets exactly ONE entrance door on external wall
- **Garage band (DONE 2026-07-07)**: a garage is a footprint outlier — it gets its OWN full-width band at the back (max-y = north = cold-side thermal buffer), never inside the two shared bands (it used to inflate the min-side width raise until the wet band collapsed — the "kitchen ~1.3 m" shortfall, now fixed). Garage doors are planned in `_assign_garage_doors`, not grown by the BFS: 2.4 m vehicle gate on an external wall (corner-aligned, so the window fits beside it) + person-door into a mudroom-order neighbour (`_GARAGE_DOOR_PREF`: utility > kitchen > hallway > living; bath/toilet and bedrooms last — a bedroom parent would trip rule 4). Garage is pinned to the ground floor in `_distribute_floors` (cars do not climb stairs). `_assign_windows` skips a window that would land inside any same-wall door (the gate case). Tests: `backend/tests/test_garage_band.py`.
- `LLMLayoutEngine` in `llm_layout_engine.py` wraps `LayoutEngine` with Groq agentic loop (5 iterations → fallback to rule-based)

### Invariants (`backend/core/plan_invariants.py`)
9 rules enforced deterministically after every generation:
1. No overlaps + coverage ≥ 90% of bbox
2. Areas ≥ 90% of requested
3. Every room has a door
4. No transit through bedroom to reach circulation
5. Wet zones share one riser per floor
6. Entrance via hallway buffer (`EXT_DOOR_OK` exempts the garage — a vehicle gate is not the pedestrian entrance, the garage is its own unheated buffer)
7. Wet-over-wet across floors
8. Mandatory: kitchen + bathroom/toilet
9. Min usable dimension (uses `USABLE_MIN_SIDE`)

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

## Known issues / current work (as of 2026-07-07)
- Habitable min side is **2.4 m** (`USABLE_MIN_SIDE`) and that is the engine's FEASIBLE floor, not a preference: raising living/bedroom to 2.6–2.7 starves the wet band below the kitchen's min (the shared central-hall width is driven up by the narrowest habitable room), making the engine's own output fail rule 9. The garage half of the redesign is DONE (garage band); 2.6–2.7 still needs the shared-width coupling between the two remaining bands rethought. The LLM path is gated by the SAME table via `plan_validator.MIN_SIDE` (derived from `USABLE_MIN_SIDE`), so LLM "pencil" rooms (2.0–2.3 m) are rejected → rule-engine fallback.
- ~~Garage-heavy programs hit an honest wet-band shortfall (kitchen ~1.3 m)~~ — FIXED 2026-07-07 by the garage band (see Layout engine section); small-bedroom-only programs can still trip rule 9, shipped as best-effort.
- Conflict dots on 2D plan have hover tooltips (severity + description + localized `mepHints.*` hint) via the shared floating `hover-card`; hit area is a transparent r=0.34 circle with `cursor: help` (DONE 2026-07-03)

### Displayed area = ACTUAL footprint (single definition)
- Room area shown on the 2D canvas AND in the PDF (per-room + floor total) is `width × depth` (the real tiled footprint), NOT the requested `area_m2`. They diverged before (e.g. the full-width hallway: requested 4.8 m² but actual 8.4×1.3 = 10.9 m²), which made canvas (Σ area_m2) ≠ PDF/gabarit (Σ w×d) and the PDF internally inconsistent (header vs room table). `area_m2` stays the requested value (used by invariant rule 2 only).
- Cost display is locale-driven: local currency primary (KZ→KZT, RU→RUB), USD secondary; US shows USD only (`ResultsPanel` cost card).

## Coding rules (enforced by user)
- Karpathy method: diagnose → write failing test → fix
- No comments unless WHY is non-obvious
- No backwards-compat shims for removed code
- Tailwind v3 only (no v4 syntax)
- Touch 3D viewer (`ThreeViewer.tsx`) only if explicitly asked
- Never mock the database / external services in tests that are meant to catch real integration bugs
- RUB primary currency for RU/KZ, USD secondary

## Self-rules — mistakes already made here, do NOT repeat them
These cost real cycles. Read before touching shell, geometry, or adding UI/metrics.

### Windows / shell
- git-bash `/tmp` ≠ Windows-Python `/tmp` (the latter is `C:\tmp`). When a bash command (e.g. `curl -o`) writes a file a Windows exe (`python.exe`) then reads, use a RELATIVE path in a shared cwd or a `C:/...` path — never `/tmp`. (Lost 2 cycles to "FileNotFound".)
- In bash heredocs, Windows paths with `\` get mangled (`C:\\Program Files` → backslashes stripped → broken path). Use FORWARD slashes for Windows paths in any script written via heredoc — Node and Python accept them.
- Foreground `sleep` is blocked; never chain `sleep N && cmd`. Use `run_in_background` or Monitor.
- PowerShell cwd persists between tool calls — re-`cd` into the dir you're already in errors. Check first.

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

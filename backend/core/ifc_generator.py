"""
IFC file generation via IfcOpenShell.
Generates walls, slabs, openings and MEP placeholders.
"""
import os
import math
import uuid
from datetime import datetime
from typing import List, Optional

try:
    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.util.element
    IFC_AVAILABLE = True
except ImportError:
    IFC_AVAILABLE = False

from models import BuildingParams, GeoClimateData, RoomLayout, RoomType, DoorSpec, WindowSpec
from config import settings  # noqa: E402

FLOOR_HEIGHT = 3.0  # metres per storey


class IFCGenerator:
    def __init__(
        self,
        project_id: str,
        params: BuildingParams,
        rooms: List[RoomLayout],
        pipes: list,
        geo: GeoClimateData,
    ):
        self.project_id = project_id
        self.params = params
        self.rooms = rooms
        self.pipes = pipes
        self.geo = geo
        self.ifc = None

    def generate(self) -> str:
        if not IFC_AVAILABLE:
            return self._generate_stub()
        self.ifc = ifcopenshell.api.run("project.create_file", version="IFC4")

        project = ifcopenshell.api.run(
            "root.create_entity", self.ifc, ifc_class="IfcProject", name="ArchVision Project"
        )
        ifcopenshell.api.run(
            "unit.assign_unit", self.ifc, length={"is_metric": True, "raw": "METRES"}
        )

        context = ifcopenshell.api.run(
            "context.add_context", self.ifc, context_type="Model"
        )
        body = ifcopenshell.api.run(
            "context.add_context",
            self.ifc,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=context,
        )

        site = ifcopenshell.api.run(
            "root.create_entity", self.ifc, ifc_class="IfcSite", name="Site"
        )
        building = ifcopenshell.api.run(
            "root.create_entity", self.ifc, ifc_class="IfcBuilding", name="ArchVision Building"
        )
        ifcopenshell.api.run(
            "aggregate.assign_object", self.ifc, relating_object=project, products=[site]
        )
        ifcopenshell.api.run(
            "aggregate.assign_object", self.ifc, relating_object=site, products=[building]
        )

        # Group rooms by floor
        floors: dict[int, List[RoomLayout]] = {}
        for room in self.rooms:
            floors.setdefault(room.floor, []).append(room)

        for floor_num in sorted(floors.keys()):
            elevation = (floor_num - 1) * FLOOR_HEIGHT
            storey = ifcopenshell.api.run(
                "root.create_entity",
                self.ifc,
                ifc_class="IfcBuildingStorey",
                name=f"Floor {floor_num}",
            )
            ifcopenshell.api.run(
                "attribute.edit_attributes",
                self.ifc,
                product=storey,
                attributes={"Elevation": elevation},
            )
            ifcopenshell.api.run(
                "aggregate.assign_object",
                self.ifc,
                relating_object=building,
                products=[storey],
            )

            wall_t = self.geo.wall_thickness_mm / 1000.0

            for room in floors[floor_num]:
                self._add_space(storey, body, room, elevation, wall_t)
                for door in room.doors:
                    self._add_door(storey, body, room, door, elevation)
                for win in room.windows:
                    self._add_window(storey, body, room, win, elevation)

            # Foundation slab on ground floor
            if floor_num == 1:
                self._add_foundation_slab(storey, body, floors[floor_num], elevation, wall_t)

        out_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{self.project_id}.ifc")
        self.ifc.write(out_path)
        return out_path

    def _generate_stub(self) -> str:
        """Fallback when ifcopenshell is not installed: writes a minimal valid IFC4 stub."""
        os.makedirs(settings.IFC_OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(settings.IFC_OUTPUT_DIR, f"{self.project_id}.ifc")
        stub = (
            "ISO-10303-21;\n"
            "HEADER;\nFILE_DESCRIPTION(('ArchVision AI stub'),'2;1');\n"
            f"FILE_NAME('{self.project_id}.ifc','2024-01-01',(),(),'ArchVision','','');\n"
            "FILE_SCHEMA(('IFC4'));\nENDSEC;\n"
            "DATA;\n"
            "#1=IFCPROJECT('stub',$,'ArchVision Project',$,$,$,$,$,$);\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        with open(out_path, "w") as f:
            f.write(stub)
        return out_path

    def _add_space(self, storey, body, room: RoomLayout, elevation: float, wall_t: float):
        space = ifcopenshell.api.run(
            "root.create_entity",
            self.ifc,
            ifc_class="IfcSpace",
            name=room.name,
        )
        ifcopenshell.api.run(
            "aggregate.assign_object", self.ifc, relating_object=storey, products=[space]
        )

        # Walls: 4 sides
        walls_data = [
            # (start_x, start_y, dx, dy)
            (room.x, room.y, room.width, 0),
            (room.x + room.width, room.y, 0, room.depth),
            (room.x + room.width, room.y + room.depth, -room.width, 0),
            (room.x, room.y + room.depth, 0, -room.depth),
        ]
        for wx, wy, dx, dy in walls_data:
            self._add_wall(storey, body, wx, wy, elevation, dx, dy, wall_t)

        # Slab (floor of the space)
        self._add_slab(storey, body, room, elevation)

    def _add_wall(self, storey, body, x, y, elevation, dx, dy, thickness):
        wall = ifcopenshell.api.run(
            "root.create_entity", self.ifc, ifc_class="IfcWall"
        )
        ifcopenshell.api.run(
            "spatial.assign_container", self.ifc, relating_structure=storey, products=[wall]
        )
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.01:
            return

        # Placement
        placement = self.ifc.createIfcLocalPlacement(
            None,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([x, y, elevation]),
                self.ifc.createIfcDirection([0.0, 0.0, 1.0]),
                self.ifc.createIfcDirection([dx / length, dy / length, 0.0]),
            ),
        )
        wall.ObjectPlacement = placement

        # Shape: rectangular profile extruded
        profile = self.ifc.createIfcRectangleProfileDef(
            "AREA", None,
            self.ifc.createIfcAxis2Placement2D(
                self.ifc.createIfcCartesianPoint([0.0, 0.0])
            ),
            length,
            thickness,
        )
        extruded = self.ifc.createIfcExtrudedAreaSolid(
            profile,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([0.0, 0.0, 0.0])
            ),
            self.ifc.createIfcDirection([0.0, 0.0, 1.0]),
            FLOOR_HEIGHT,
        )
        shape = self.ifc.createIfcShapeRepresentation(
            body, "Body", "SweptSolid", [extruded]
        )
        wall.Representation = self.ifc.createIfcProductDefinitionShape(None, None, [shape])

    def _add_slab(self, storey, body, room: RoomLayout, elevation: float):
        slab = ifcopenshell.api.run(
            "root.create_entity", self.ifc, ifc_class="IfcSlab"
        )
        ifcopenshell.api.run(
            "spatial.assign_container", self.ifc, relating_structure=storey, products=[slab]
        )
        placement = self.ifc.createIfcLocalPlacement(
            None,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([room.x, room.y, elevation]),
            ),
        )
        slab.ObjectPlacement = placement
        profile = self.ifc.createIfcRectangleProfileDef(
            "AREA", None,
            self.ifc.createIfcAxis2Placement2D(
                self.ifc.createIfcCartesianPoint([0.0, 0.0])
            ),
            room.width,
            room.depth,
        )
        extruded = self.ifc.createIfcExtrudedAreaSolid(
            profile,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([0.0, 0.0, 0.0])
            ),
            self.ifc.createIfcDirection([0.0, 0.0, 1.0]),
            0.2,  # 200mm slab
        )
        shape = self.ifc.createIfcShapeRepresentation(body, "Body", "SweptSolid", [extruded])
        slab.Representation = self.ifc.createIfcProductDefinitionShape(None, None, [shape])

    def _wall_origin(self, room: RoomLayout, door: "DoorSpec | WindowSpec", elevation: float):
        """World XY origin of an opening's wall start point."""
        if door.wall == "S":
            return room.x + door.position, room.y, 0.0, 1.0
        if door.wall == "N":
            return room.x + door.position, room.y + room.depth, 0.0, 1.0
        if door.wall == "W":
            return room.x, room.y + door.position, 1.0, 0.0
        # E
        return room.x + room.width, room.y + door.position, 1.0, 0.0

    def _add_door(self, storey, body, room: RoomLayout, door: DoorSpec, elevation: float):
        if not IFC_AVAILABLE:
            return
        ox, oy, dx, dy = self._wall_origin(room, door, elevation)
        entity = ifcopenshell.api.run("root.create_entity", self.ifc, ifc_class="IfcDoor")
        ifcopenshell.api.run("spatial.assign_container", self.ifc, relating_structure=storey, products=[entity])
        placement = self.ifc.createIfcLocalPlacement(
            None,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([ox, oy, elevation]),
                self.ifc.createIfcDirection([0.0, 0.0, 1.0]),
                self.ifc.createIfcDirection([dx, dy, 0.0]),
            ),
        )
        entity.ObjectPlacement = placement
        ifcopenshell.api.run(
            "attribute.edit_attributes", self.ifc, product=entity,
            attributes={"OverallWidth": door.width, "OverallHeight": 2.1},
        )

    def _add_window(self, storey, body, room: RoomLayout, win: WindowSpec, elevation: float):
        if not IFC_AVAILABLE:
            return
        ox, oy, dx, dy = self._wall_origin(room, win, elevation)
        entity = ifcopenshell.api.run("root.create_entity", self.ifc, ifc_class="IfcWindow")
        ifcopenshell.api.run("spatial.assign_container", self.ifc, relating_structure=storey, products=[entity])
        placement = self.ifc.createIfcLocalPlacement(
            None,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([ox, oy, elevation + win.sill]),
                self.ifc.createIfcDirection([0.0, 0.0, 1.0]),
                self.ifc.createIfcDirection([dx, dy, 0.0]),
            ),
        )
        entity.ObjectPlacement = placement
        ifcopenshell.api.run(
            "attribute.edit_attributes", self.ifc, product=entity,
            attributes={"OverallWidth": win.width, "OverallHeight": win.height},
        )

    def _add_foundation_slab(self, storey, body, rooms: List[RoomLayout], elevation: float, wall_t: float):
        if not rooms:
            return
        min_x = min(r.x for r in rooms)
        min_y = min(r.y for r in rooms)
        max_x = max(r.x + r.width for r in rooms)
        max_y = max(r.y + r.depth for r in rooms)
        width = max_x - min_x + wall_t * 2
        depth = max_y - min_y + wall_t * 2

        foundation = ifcopenshell.api.run(
            "root.create_entity", self.ifc, ifc_class="IfcFooting"
        )
        ifcopenshell.api.run(
            "spatial.assign_container", self.ifc, relating_structure=storey, products=[foundation]
        )
        fd = self.geo.frost_depth_m
        z_offset = -(fd + 0.3)  # 300mm below frost line
        placement = self.ifc.createIfcLocalPlacement(
            None,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([min_x - wall_t, min_y - wall_t, z_offset])
            ),
        )
        foundation.ObjectPlacement = placement
        profile = self.ifc.createIfcRectangleProfileDef(
            "AREA", None,
            self.ifc.createIfcAxis2Placement2D(
                self.ifc.createIfcCartesianPoint([0.0, 0.0])
            ),
            width,
            depth,
        )
        extruded = self.ifc.createIfcExtrudedAreaSolid(
            profile,
            self.ifc.createIfcAxis2Placement3D(
                self.ifc.createIfcCartesianPoint([0.0, 0.0, 0.0])
            ),
            self.ifc.createIfcDirection([0.0, 0.0, 1.0]),
            0.4,
        )
        shape = self.ifc.createIfcShapeRepresentation(body, "Body", "SweptSolid", [extruded])
        foundation.Representation = self.ifc.createIfcProductDefinitionShape(None, None, [shape])

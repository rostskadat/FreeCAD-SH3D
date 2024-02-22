#***************************************************************************
#*   Copyright (c) 2024 Julien Masnada <rostskadat@gmail.com>              *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

from functools import partial
from PySide.QtCore import QT_TRANSLATE_NOOP
from zipfile import ZipFile

import Arch
import Draft
import DraftGeomUtils
import DraftVecUtils
import FreeCAD
import FreeCADGui
import Mesh
import WorkingPlane

import numpy
import math
import os
import uuid
import xml.etree.ElementTree as ET

# SweetHome3D is in cm while FreeCAD is in mm
FACTOR = 10
DEBUG = False
DEBUG_COLOR = (255, 0, 0)

RENDER_AVAILABLE = True

try:
    import Render
except:
    FreeCAD.Console.PrintWarning("Render is not available. Not creating any lights.\n")
    RENDER_AVAILABLE = False

# This hash contains the document elemnt with their SH3D id as key
shoul_merge_elements = True
document_elements = {}

def import_sh3d(filename, join_walls=True, merge_elements=True, import_doors=True, import_furnitures=True, import_lights=True, import_cameras=True, progress_callback=None):
    """Import a SweetHome 3D file into the current document.

    Args:
        filename (str): the filename of the document to import
        join_wall (bool, optional): whether to join walls. Defaults to True.
        merge_elements (bool, optional): whether SH3D elment should be merged with existing elements. Defaults to True.
        import_doors (bool, optional): whether to import doors. Defaults to True.
        import_furnitures (bool, optional): whether to import furnitures. Defaults to True.
        import_lights (bool, optional): whether to import lights. Defaults to True.
        import_cameras (bool, optional): whether to import cameras. Defaults to True.
        progress_callback (func): a function to set the progress porcentage and the status. Defaults to None.

    Raises:
        ValueError: If the document is an invalid SweetHome 3D document
    """
    if not progress_callback:
        def progress_callback(progress, status):
            FreeCAD.Console.PrintLog(f"{status} ({progress}/100)\n")

    global shoul_merge_elements
    global document_elements
    shoul_merge_elements = merge_elements
    if merge_elements:

        for object in FreeCAD.ActiveDocument.Objects:
            if hasattr(object, 'id'):
                document_elements[object.id] = object

    with ZipFile(filename, 'r') as zip:
        entries = zip.namelist()
        if "Home.xml" not in entries:
            raise ValueError("Invalid SweetHome3D file: missing Home.xml")
        home = ET.fromstring(zip.read("Home.xml"))

        document = FreeCAD.ActiveDocument
        if import_furnitures and (not merge_elements or not document.getObject("Baseboards")):
            document.addObject("App::DocumentObjectGroup","Baseboards")
        if import_furnitures and (not merge_elements or not document.getObject("Furnitures")):
            document.addObject("App::DocumentObjectGroup","Furnitures")
        if import_lights and (not merge_elements or not document.getObject("Lights")):
            document.addObject("App::DocumentObjectGroup","Lights")
        if import_cameras and (not merge_elements or not document.getObject("Cameras")):
            document.addObject("App::DocumentObjectGroup","Cameras")

        progress_callback(0, "Importing levels ...")
        if home.findall('level'):
            floors = _import_levels(home)
        else:
            floors = [_create_default_floor()]

        progress_callback(10, "Importing rooms ...")
        _import_rooms(home, floors)

        progress_callback(20, "Importing walls ...")
        _import_walls(home, floors, import_furnitures)

        progress_callback(30, "Importing doors ...")
        if import_doors:
            FreeCAD.ActiveDocument.recompute()
            _import_doors(home, floors)

        progress_callback(40, "Importing furnitues ...")
        if import_furnitures:
            FreeCAD.ActiveDocument.recompute()
            _import_furnitures(home, zip, floors)

        progress_callback(50, "Importing lights ...")
        if import_lights:
            FreeCAD.ActiveDocument.recompute()
            _import_lights(home, zip, floors)

        progress_callback(60, "Importing cameras ...")
        if import_cameras:
            FreeCAD.ActiveDocument.recompute()
            _import_observer_cameras(home)

        progress_callback(70, "Creating Arch::Site ...")

        name = home.get('name')
        building = None
        if shoul_merge_elements:
            building = _get_element_to_merge({'id':name}, 'building')

        if not building:
            building = Arch.makeBuilding(floors)
            _add_property(building, "App::PropertyString", "shType", "The element type")
            _add_property(building, "App::PropertyString", "id", "The element's id")
            building.shType = 'building'
            building.id = name
            Arch.makeSite([ building ])
            Arch.makeProject([ ])

        # TODO: Should be set only when opening a file, not when importing
        document.Label = name
        document.CreatedBy = _get_sh3d_property(home, 'Author', '')
        document.Comment = _get_sh3d_property(home, 'Copyright', '')
        document.License = _get_sh3d_property(home, 'License', '')

        progress_callback(100, "Successfully imported data.")


    FreeCAD.activeDocument().recompute()
    if FreeCAD.GuiUp:
        FreeCADGui.SendMsgToActiveView("ViewFit")

def _import_levels(home):
    """Returns all the levels found in the file.

    Args:
        home (dict): The xml to read the objects from

    Returns:
        list: the list of imported floors
    """
    return list(map(_import_level, enumerate(home.findall('level'))))

def _import_level(imported_tuple):
    """Creates and returns a Arch::Floor from the imported_level object

    Args:
        imported_tuple (tuple): a tuple containing the index and the
            dict object containg the characteristics of the new object

    Returns:
        Arc::Floor: the newly created object
    """
    (i, imported_level) = imported_tuple

    floor = None
    if shoul_merge_elements:
        floor = _get_element_to_merge(imported_level, 'level')

    if not floor:
        floor = Arch.makeFloor()
    floor.Label = imported_level.get('name')
    floor.Placement.Base.z = _dim_sh2fc(float(imported_level.get('elevation')))
    floor.Height = _dim_sh2fc(float(imported_level.get('height')))

    #floor.setExpression("OverallWidth", "Length.Value")

    _add_property(floor, "App::PropertyString", "shType", "The element type")
    _add_property(floor, "App::PropertyString", "id", "The floor's id")
    _add_property(floor, "App::PropertyFloat", "floorThickness", "The floor's slab thickness")
    _add_property(floor, "App::PropertyInteger", "elevationIndex", "The floor number")
    _add_property(floor, "App::PropertyBool", "viewable", "Whether the floor is viewable")

    floor.shType         = 'level'
    floor.id             = imported_level.get('id')
    floor.floorThickness = _dim_sh2fc(float(imported_level.get('floorThickness')))
    floor.elevationIndex = int(imported_level.get('elevationIndex', 0))
    floor.ViewObject.Visibility = imported_level.get('visible', 'false') == 'true'

    if i != 0 and i % 5 and FreeCAD.GuiUp:
        FreeCADGui.updateGui()
        FreeCADGui.SendMsgToActiveView("ViewFit")

    return floor

def _create_default_floor():

    default_floor = None
    if shoul_merge_elements:
        default_floor = _get_element_to_merge({'id':"default-floor"}, 'level')

    if not default_floor:
        default_floor = Arch.makeFloor()

    default_floor.Label = 'Floor'
    default_floor.Placement.Base.z = 0
    default_floor.Height = 2500

    _add_property(default_floor, "App::PropertyString", "shType", "The element type")
    _add_property(default_floor, "App::PropertyString", "id", "The floor id")
    _add_property(default_floor, "App::PropertyFloat", "floorThickness", "The floor's slab thickness")

    default_floor.shType         = 'level'
    default_floor.id             = "default-floor"
    default_floor.floorThickness = 200

    return default_floor

def _get_floor(floors, level_id):
    """Returns the Floor associated with the level_id.

    Returns the first level if there is just one level.

    Args:
        levels (list): The list of imported levels
        level_id (string): the level @id

    Returns:
        level: The level
    """
    if len(floors) == 1 or not level_id:
        return floors[0]
    return dict(map(lambda f: (f.id, f), floors))[level_id]

def _import_rooms(home, floors):
    """Returns all the rooms found in the file.

    Args:
        home (dict): The xml to read the objects from

    Returns:
        list: the list of imported rooms
    """
    return list(map(partial(_import_room, floors), enumerate(home.findall('room'))))

def _import_room(floors, imported_tuple):
    """Creates and returns a Arch::Structure from the imported_room object

    Args:
        imported_tuple (tuple): a tuple containing the index and the
            dict object containg the characteristics of the new object

    Returns:
        Arc::Structure: the newly created object
    """
    (i, imported_room) = imported_tuple
    floor = _get_floor(floors, imported_room.get('level'))

    pl = FreeCAD.Placement()
    points = []
    for point in imported_room.findall('point'):
        x = float(point.get('x'))
        y = float(point.get('y'))
        z = _dim_fc2sh(floor.Placement.Base.z)
        points.append(_coord_sh2fc(FreeCAD.Vector(x, y, z)))

    slab = None
    if shoul_merge_elements:
        slab = _get_element_to_merge(imported_room, 'room')

    if not slab:
        line = Draft.make_wire(points, placement=pl, closed=True, face=True, support=None)
        slab = Arch.makeStructure(line, height=floor.floorThickness)

    slab.Label = imported_room.get('name', 'Room')
    slab.IfcType = "Slab"
    slab.Normal = FreeCAD.Vector(0,0,-1)

    pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/SH3D")
    defaultFloorColor = pref.GetString("defaultFloorColor", 'FF96A9BA')

    _set_color_and_transparency(slab, imported_room.get('floorColor', defaultFloorColor))
    # ceilingColor is not imported in the model as it depends on the upper room

    _add_property(slab, "App::PropertyString", "shType", "The element type")
    _add_property(slab, "App::PropertyString", "id", "The slab's id")
    _add_property(slab, "App::PropertyFloat", "nameAngle", "The room's name angle")
    _add_property(slab, "App::PropertyFloat", "nameXOffset", "The room's name x offset")
    _add_property(slab, "App::PropertyFloat", "nameYOffset", "The room's name y offset")
    _add_property(slab, "App::PropertyBool", "areaVisible", "Whether the area of the room is displayed in the plan view")
    _add_property(slab, "App::PropertyFloat", "areaAngle", "The room's area annotation angle")
    _add_property(slab, "App::PropertyFloat", "areaXOffset", "The room's area annotation x offset")
    _add_property(slab, "App::PropertyFloat", "areaYOffset", "The room's area annotation y offset")
    _add_property(slab, "App::PropertyBool", "floorVisible", "Whether the floor of the room is displayed")
    _add_property(slab, "App::PropertyString", "floorColor", "The room's floor color")
    _add_property(slab, "App::PropertyFloat", "floorShininess", "The room's floor shininess")
    _add_property(slab, "App::PropertyBool", "ceilingVisible", "Whether the ceiling of the room is displayed")
    _add_property(slab, "App::PropertyString", "ceilingColor", "The room's ceiling color")
    _add_property(slab, "App::PropertyFloat", "ceilingShininess", "The room's ceiling shininess")
    _add_property(slab, "App::PropertyBool", "ceilingFlat", "")

    slab.shType = 'room'
    slab.id = imported_room.get('id', str(uuid.uuid4()))
    slab.nameAngle = float(imported_room.get('nameAngle', 0))
    slab.nameXOffset = float(imported_room.get('nameXOffset', 0))
    slab.nameYOffset = float(imported_room.get('nameYOffset', -400))
    slab.areaVisible = bool(imported_room.get('areaVisible', False))
    slab.areaAngle = float(imported_room.get('areaAngle', 0))
    slab.areaXOffset = float(imported_room.get('areaXOffset', 0))
    slab.areaYOffset = float(imported_room.get('areaYOffset', 0))
    slab.floorVisible = bool(imported_room.get('floorVisible', True))
    slab.floorColor = str(imported_room.get('floorColor', 'FF96A9BA'))
    slab.floorShininess = float(imported_room.get('floorShininess', 0))
    slab.ceilingVisible = bool(imported_room.get('ceilingVisible', True))
    slab.ceilingColor = str(imported_room.get('ceilingColor', 'FF000000'))
    slab.ceilingShininess = float(imported_room.get('ceilingShininess', 0))
    slab.ceilingFlat = bool(imported_room.get('ceilingFlat', False))

    floor.addObject(slab)

    if i != 0 and i % 5 and FreeCAD.GuiUp:
        FreeCADGui.updateGui()
        FreeCADGui.SendMsgToActiveView("ViewFit")

    return slab

def _import_walls(home, floors, import_baseboards):
    """Returns the list of imported walls

    Args:
        home (dict): The xml to read the objects from
        floors (list): The list of floor each wall references
        import_baseboards (bool): whether baseboard should also be imported

    Returns:
        list: the list of imported walls
    """
    return list(map(partial(_import_wall, floors, import_baseboards), enumerate(home.findall('wall'))))

def _import_wall(floors, import_baseboards, imported_tuple):
    """Creates and returns a Arch::Structure from the imported_wall object

    Args:
        imported_tuple (tuple): a tuple containing the index and the
            dict object containg the characteristics of the new object

    Returns:
        Arc::Structure: the newly created object
    """
    (i, imported_wall) = imported_tuple

    floor = _get_floor(floors, imported_wall.get('level'))

    wall = None
    if shoul_merge_elements:
        wall = _get_element_to_merge(imported_wall, 'wall')

    if not wall:
        invert_angle = False
        if imported_wall.get('arcExtent'):
            wall, invert_angle = _make_arqued_wall(floor, imported_wall)
        elif imported_wall.get('heightAtEnd'):
            wall = _make_tappered_wall(floor, imported_wall)
        else:
            wall = _make_straight_wall(floor, imported_wall)

    _set_wall_colors(wall, imported_wall, invert_angle)
    wall.IfcType = "Wall"

    _add_property(wall, "App::PropertyString", "shType", "The element type")
    _add_property(wall, "App::PropertyString", "id", "The wall's id")
    _add_property(wall, "App::PropertyString", "wallAtStart", "The Id of the contiguous wall at the start of this wall")
    _add_property(wall, "App::PropertyString", "wallAtEnd", "The Id of the contiguous wall at the end of this wall")
    _add_property(wall, "App::PropertyString", "pattern", "The pattern of this wall in plan view")
    _add_property(wall, "App::PropertyFloat", "leftSideShininess", "The wall's left hand side shininess")
    _add_property(wall, "App::PropertyFloat", "rightSideShininess", "The wall's right hand side shininess")

    wall.shType = 'wall'
    wall.id = imported_wall.get('id')
    wall.wallAtStart = imported_wall.get('wallAtStart', '')
    wall.wallAtEnd = imported_wall.get('wallAtEnd', '')
    wall.pattern = imported_wall.get('pattern', '')
    wall.leftSideShininess = float(imported_wall.get('leftSideShininess', 0))
    wall.rightSideShininess = float(imported_wall.get('rightSideShininess', 0))

    floor.addObject(wall)

    if import_baseboards:
        FreeCAD.ActiveDocument.recompute()
        baseboards = _import_baseboards(wall, imported_wall)
        if len(baseboards):
            FreeCAD.ActiveDocument.Baseboards.addObjects(baseboards)

    if i != 0 and i % 5 and FreeCAD.GuiUp:
        FreeCADGui.updateGui()
        FreeCADGui.SendMsgToActiveView("ViewFit")

    return wall

def _make_straight_wall(floor, imported_wall):
    """Create a Arch Wall from a line.

    The constructed wall will be a simple solid with the length width height found in imported_wall

    Args:
        floor (Arch::Structure): The floor the wall belongs to
        imported_wall (dict): the imported wall

    Returns:
        Arch::Wall: the newly created wall
    """
    x_start = float(imported_wall.get('xStart'))
    y_start = float(imported_wall.get('yStart'))
    z_start = _dim_fc2sh(floor.Placement.Base.z)
    x_end = float(imported_wall.get('xEnd'))
    y_end = float(imported_wall.get('yEnd'))

    pl = FreeCAD.Placement()
    points = [
        _coord_sh2fc(FreeCAD.Vector(x_start, y_start, z_start)),
        _coord_sh2fc(FreeCAD.Vector(x_end, y_end, z_start))
    ]
    line = Draft.make_wire(points, placement=pl, closed=False, face=True, support=None)
    wall = Arch.makeWall(line)

    #wall.setExpression('Height', f"<<{floor}>>.height")
    wall.Height = _dim_sh2fc(imported_wall.get('height', _dim_fc2sh(floor.Height)))
    wall.Width = _dim_sh2fc(imported_wall.get('thickness'))
    wall.Normal = FreeCAD.Vector(0, 0, 1)
    return wall

def _make_tappered_wall(floor, imported_wall):
    #
    # We draw the vertical profile of the wall and then we extrude the
    # resulting shape. Finally we transform this shape into an Arch::Wall
    #
    x_start = float(imported_wall.get('xStart'))
    y_start = float(imported_wall.get('yStart'))
    x_end = float(imported_wall.get('xEnd'))
    y_end = float(imported_wall.get('yEnd'))
    z = _dim_fc2sh(floor.Placement.Base.z)

    height_at_start = float(imported_wall.get('height', _dim_fc2sh(floor.Height)))
    height_at_end = float(imported_wall.get('heightAtEnd', height_at_start))

    points = [
        _coord_sh2fc(FreeCAD.Vector(x_start, y_start, z)),
        _coord_sh2fc(FreeCAD.Vector(x_end, y_end, z)),
        _coord_sh2fc(FreeCAD.Vector(x_end, y_end, z+height_at_end)),
        _coord_sh2fc(FreeCAD.Vector(x_start, y_start, z+height_at_start)),
    ]
    profile = Draft.make_wire(points, closed=True, face=True)
    width = _dim_sh2fc(imported_wall.get('thickness'))
    extrusion = FreeCAD.ActiveDocument.addObject('Part::Extrusion', imported_wall.get('id'))
    extrusion.Base = profile
    extrusion.DirMode = "Custom"
    extrusion.Dir = WorkingPlane.DraftGeomUtils.getNormal(points)
    extrusion.LengthFwd = width
    extrusion.Symmetric = True
    profile.Visibility = False
    wall = Arch.makeWall(extrusion)
    return wall

def _make_arqued_wall(floor, imported_wall):

    x1 = float(imported_wall.get('xStart'))
    y1 = float(imported_wall.get('yStart'))
    x2 = float(imported_wall.get('xEnd'))
    y2 = float(imported_wall.get('yEnd'))
    z = _dim_fc2sh(floor.Placement.Base.z)

    # p1 and p2 are the points at which the arc should pass, i.e. the center
    #   of the edge used to draw the rectangle (used later on as sections)
    p1 = _coord_sh2fc(FreeCAD.Vector(x1, y1, z))
    p2 = _coord_sh2fc(FreeCAD.Vector(x2, y2, z))

    thickness = _dim_sh2fc(imported_wall.get('thickness'))
    arc_extent = _ang_sh2fc(imported_wall.get('arcExtent', 0))
    height1 = _dim_sh2fc(imported_wall.get('height', _dim_fc2sh(floor.Height)))
    height2 = _dim_sh2fc(imported_wall.get('heightAtEnd', _dim_fc2sh(height1)))

    # FROM HERE ALL IS IN FC COORDINATE

    # Calculate the circle that pases through the center of both rectangle
    #   and has the correct angle betwen p1 and p2
    chord = DraftVecUtils.dist(p1, p2)
    radius = abs(chord / (2*math.sin(arc_extent/2)))

    circles = DraftGeomUtils.circleFrom2PointsRadius(p1, p2, radius)
    # We take the center that preserve the arc_extent orientation (in FC 
    #   coordinate). The orientation is calculated from p1 to p2
    invert_angle = False
    center = circles[0].Center
    if numpy.sign(arc_extent) != numpy.sign(DraftVecUtils.angle(p1-center, p2-center)):
        invert_angle = True
        center = circles[1].Center

    # radius1 and radius2 are the vector from center to p1 and p2 respectively
    radius1 = p1-center
    radius2 = p2-center

    # NOTE: FreeCAD.Vector.getAngle return unsigned angle, using
    #   DraftVecUtils.angle instead
    # a1 and a2 are the angle between each etremity radius and the unit vector
    #   they are used to determine the rotation for the section used to draw
    #   the wall.
    a1 = math.degrees(DraftVecUtils.angle(FreeCAD.Vector(1,0,0), radius1))
    a2 = math.degrees(DraftVecUtils.angle(FreeCAD.Vector(1,0,0), radius2))

    if DEBUG:
        p1C1p2 = numpy.sign(DraftVecUtils.angle(p1-circles[0].Center, p2-circles[0].Center))
        p1C2p2 = numpy.sign(DraftVecUtils.angle(p1-circles[1].Center, p2-circles[1].Center))
        print (f"{imported_wall.get('id')}: arc_extent={round(math.degrees(arc_extent))}, sign(C1)={p1C1p2}, sign(C2)={p1C2p2}, c={center}, a1={round(a1)}, a2={round(a2)}")

    # Place the 1st section.
    # The rectamgle is oriented vertically and normal to the radius (ZYX)
    # NOTE: That we adjust the placement origin with the wall thickness, as
    #   the rectangle is placed using its corner (not the center of the edge
    #   used to draw it).
    p_corner = FreeCAD.Placement(FreeCAD.Vector(-thickness/2), FreeCAD.Rotation())
    r1 = FreeCAD.Rotation(a1, 0, 90)
    placement1 = FreeCAD.Placement(p1, r1) * p_corner
    section1 = Draft.make_rectangle(thickness, height1, placement1)

    # Place the 2nd section. Rotation (ZYX)
    r2 = FreeCAD.Rotation(a2, 0, 90)
    placement2 = FreeCAD.Placement(p2, r2) * p_corner
    section2 = Draft.make_rectangle(thickness, height2, placement2)

    if DEBUG:
        section1.ViewObject.LineColor = DEBUG_COLOR
        section2.ViewObject.LineColor = DEBUG_COLOR

        origin = FreeCAD.Vector(0,0,0)
        g = FreeCAD.ActiveDocument.addObject("App::DocumentObjectGroup", imported_wall.get('id'))

        def _debug_transformation(label, center, thickness, height, angle, point):
            p = Draft.make_point(center.x, center.y, center.z, color=DEBUG_COLOR, name=f"C{label}", point_size=5)
            g.addObject(p)

            p = Draft.make_point(point.x, point.y, point.z, color=DEBUG_COLOR, name=f"P{label}", point_size=5)
            g.addObject(p)
            
            l = Draft.make_wire([origin,point])
            l.ViewObject.LineColor = DEBUG_COLOR
            l.Label = f"O-P{label}"
            g.addObject(l)

            s = Draft.make_rectangle(thickness, height)
            s.ViewObject.LineColor = DEBUG_COLOR
            s.Label = f"O-S{label}"
            g.addObject(s)

            r = FreeCAD.Rotation(0, 0, 0)
            p = FreeCAD.Placement(origin, r) * p_corner
            s = Draft.make_rectangle(thickness, height, p)
            s.ViewObject.LineColor = DEBUG_COLOR
            s.Label = f"O-S{label}-(corner)"
            g.addObject(s)

            r = FreeCAD.Rotation(angle, 0, 0)
            p = FreeCAD.Placement(origin, r) * p_corner
            s = Draft.make_rectangle(thickness, height, p)
            s.ViewObject.LineColor = DEBUG_COLOR
            s.Label = f"O-S{label}-(corner+a{label})"
            g.addObject(s)

            r = FreeCAD.Rotation(angle, 0, 90)
            p = FreeCAD.Placement(origin, r) * p_corner
            s = Draft.make_rectangle(thickness, height, p)
            s.ViewObject.LineColor = DEBUG_COLOR
            s.Label = f"O-S{label}-(corner+a{label}+90)"
            g.addObject(s)

            r = FreeCAD.Rotation(angle, 0, 90)
            p = FreeCAD.Placement(point, r) * p_corner
            s = Draft.make_rectangle(thickness, height, p)
            s.ViewObject.LineColor = DEBUG_COLOR
            s.Label = f"P{label}-S{label}-(corner+a{label}+90)"
            g.addObject(s)

        _debug_transformation("1", circles[0].Center, thickness, height1, a1, p1)
        _debug_transformation("2", circles[1].Center, thickness, height2, a2, p2)

    # Create the spine
    placement = FreeCAD.Placement(center, FreeCAD.Rotation())
    if invert_angle:
        spine = Draft.make_circle(radius, placement, False, a1, a2)
    else:
        spine = Draft.make_circle(radius, placement, False, a2, a1)

    feature = FreeCAD.ActiveDocument.addObject('Part::Sweep')
    feature.Sections = [ section1, section2 ]
    feature.Spine = spine
    feature.Solid = True
    feature.Frenet = False
    section1.Visibility = False
    section2.Visibility = False
    spine.Visibility = False
    wall = Arch.makeWall(feature)
    return wall, invert_angle

def _set_wall_colors(wall, imported_wall, invert_angle):
    # The default color of the wall
    pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/SH3D")
    defaultWallColor = pref.GetString("DefaultWallColor", 'FF96A9BA')
    topColor = imported_wall.get('topColor', defaultWallColor)
    _set_color_and_transparency(wall, topColor)
    leftSideColor = _hex2rgb(imported_wall.get('leftSideColor', topColor))
    rightSideColor = _hex2rgb(imported_wall.get('rightSideColor', topColor))
    topColor = _hex2rgb(topColor)

    # Unfortunately all faces are not defined the same way for all the wall.
    # It depends on the type of wall :o
    if imported_wall.get('arcExtent'):
        if invert_angle:
            colors = [topColor, rightSideColor, topColor, leftSideColor, topColor, topColor]
        else:
            colors = [topColor, leftSideColor, topColor, rightSideColor, topColor, topColor]
    elif imported_wall.get('heightAtEnd'):
        colors = [topColor, topColor, topColor, topColor, rightSideColor, leftSideColor]
    else:
        colors = [leftSideColor, topColor, rightSideColor, topColor, topColor, topColor]
    if hasattr(wall.ViewObject, "DiffuseColor"):
        wall.ViewObject.DiffuseColor = colors

def _import_baseboards(wall, imported_wall):
    """Returns the list of imported baseboard

    Args:
        wall (Arch::Structure): The wall the baseboard belongs to
        imported_wall (dict): The xml to read the objects from

    Returns:
        list: the list of imported baseboards
    """
    return list(map(partial(_import_baseboard, wall), imported_wall.findall('baseboard')))

def _import_baseboard(wall, imported_baseboard):
    """Creates and returns a Part::Extrusion from the imported_baseboard object

    Args:
        imported_baseboard (dict): the dict object containg the characteristics of the new object

    Returns:
        Part::Extrusion: the newly created object
    """
    wall_width = float(wall.Width)
    baseboard_width = _dim_sh2fc(imported_baseboard.get('thickness'))
    baseboard_height = _dim_sh2fc(imported_baseboard.get('height'))
    vertexes = wall.Shape.Vertexes

    # The left side is defined as the face on the left hand side when going
    # from (xStart,yStart) to (xEnd,yEnd). I assume the points are always
    # created in the same order. We then have on the lefthand side the points
    # 1 and 2, while on the righthand side we have the points 4 and 6
    side = imported_baseboard.get('attribute')
    if side == 'leftSideBaseboard':
        p_start = vertexes[0].Point
        p_end = vertexes[2].Point
        p_normal = vertexes[4].Point
    if side == 'rightSideBaseboard':
        p_start = vertexes[4].Point
        p_end = vertexes[6].Point
        p_normal = vertexes[0].Point

    v_normal = p_normal - p_start
    v_baseboard = v_normal * (baseboard_width/wall_width)
    p0 = p_start
    p1 = p_end
    p2 = p_end - v_baseboard
    p3 = p_start - v_baseboard

    baseboard_id = f"{wall.id}-{side}"
    baseboard = None
    if shoul_merge_elements:
        baseboard = _get_element_to_merge({'id':baseboard_id}, 'baseboard')

    if not baseboard:
        # I first add a rectangle
        base = Draft.make_rectangle([p0, p1, p2, p3], face=True, support=None)
        base.Visibility = False
        # and then I extrude
        baseboard = FreeCAD.ActiveDocument.addObject('Part::Extrusion', f"{wall.Label} {side}")
        baseboard.Base = base

    baseboard.DirMode = "Custom"
    baseboard.Dir = FreeCAD.Vector(0, 0, 1)
    baseboard.DirLink = None
    baseboard.LengthFwd = baseboard_height
    baseboard.LengthRev = 0
    baseboard.Solid = True
    baseboard.Reversed = False
    baseboard.Symmetric = False
    baseboard.TaperAngle = 0
    baseboard.TaperAngleRev = 0

    _set_color_and_transparency(baseboard, imported_baseboard.get('color'))

    _add_property(baseboard, "App::PropertyString", "shType", "The element type")
    _add_property(baseboard, "App::PropertyString", "id", "The element's id")
    _add_property(baseboard, "App::PropertyLink", "parent", "The element parent")

    baseboard.shType = 'baseboard'
    baseboard.id = baseboard_id
    baseboard.parent = wall

    return baseboard

def _import_doors(home, floors):
    """Returns the list of imported door

    Args:
        home (dict): The xml to read the objects from

    Returns:
        list: the list of imported doors
    """
    return list(map(partial(_import_door, floors), enumerate(home.findall('doorOrWindow'))))

def _import_door(floors, imported_tuple):
    """Creates and returns a Arch::Door from the imported_door object

    Args:
        floors (list): the list of imported levels
        imported_tuple (tuple): a tuple containing the index and the
            dict object containg the characteristics of the new object

    Returns:
        Arch::Door: the newly created object
    """
    (i, imported_door) = imported_tuple
    floor = _get_floor(floors, imported_door.get('level'))

    window = None
    if shoul_merge_elements:
        window = _get_element_to_merge(imported_door, 'doorOrWindow')

    if not window:
        window = _create_window(floor, imported_door)
        if not window:
            return None

    window.IfcType = "Window"

    _add_property(window, "App::PropertyString", "shType", "The element type")
    _add_furniture_common_attributes(window, imported_door)
    _add_piece_of_furniture_common_attributes(window, imported_door)
    _add_property(window, "App::PropertyFloat", "wallThickness", "")
    _add_property(window, "App::PropertyFloat", "wallDistance", "")
    _add_property(window, "App::PropertyFloat", "wallWidth", "")
    _add_property(window, "App::PropertyFloat", "wallLeft", "")
    _add_property(window, "App::PropertyFloat", "wallHeight", "")
    _add_property(window, "App::PropertyFloat", "wallTop", "")
    _add_property(window, "App::PropertyBool", "wallCutOutOnBothSides", "")
    _add_property(window, "App::PropertyBool", "widthDepthDeformable", "")
    _add_property(window, "App::PropertyString", "cutOutShape", "")
    _add_property(window, "App::PropertyBool", "boundToWall", "")

    window.shType = 'doorOrWindow'
    window.wallThickness = float(imported_door.get('wallThickness', 1))
    window.wallDistance = float(imported_door.get('wallDistance', 0))
    window.wallWidth = float(imported_door.get('wallWidth', 1))
    window.wallLeft = float(imported_door.get('wallLeft', 0))
    window.wallHeight = float(imported_door.get('wallHeight', 1))
    window.wallTop = float(imported_door.get('wallTop', 0))
    window.wallCutOutOnBothSides = bool(imported_door.get('wallCutOutOnBothSides', True))
    window.widthDepthDeformable = bool(imported_door.get('widthDepthDeformable', True))
    window.cutOutShape = str(imported_door.get('cutOutShape', ''))
    window.boundToWall = bool(imported_door.get('boundToWall', True))

    if i != 0 and i % 5 and FreeCAD.GuiUp:
        FreeCADGui.updateGui()

    return window

def _create_window(floor, imported_door):
    # The window in SweetHome3D s is defined with a width, depth, height.
    # Furthermore the (x.y.z) is the center point of the lower face of the
    # window. In FC the placement is defined on the face of the whole that
    # will contain the windows. The makes this calculation rather
    # cumbersome.
    x_center = float(imported_door.get('x'))
    y_center = float(imported_door.get('y'))
    z_center = float(imported_door.get('elevation', 0))
    z_center += _dim_fc2sh(floor.Placement.Base.z)

    # This is the FC coordinate of the center point of the lower face of the
    # window. This then needs to be moved to the proper face on the wall and
    # offset properly with respect to the wall's face.
    center = _coord_sh2fc(FreeCAD.Vector ( x_center, y_center, z_center ))

    wall = _get_wall(center)
    if not wall:
        FreeCAD.Console.PrintWarning(f"No wall found for door {imported_door.get('id')}. Skipping!\n")
        return None

    width = _dim_sh2fc(imported_door.get('width'))
    depth = _dim_sh2fc(imported_door.get('depth'))
    height = _dim_sh2fc(imported_door.get('height'))
    angle = float(imported_door.get('angle',0))

    # this is the vector that allow me to go from the center to the corner
    # of the bouding box. Note that the angle of the rotation is negated
    # because the y axis is reversed in SweetHome3D
    center2corner = FreeCAD.Vector( -width/2, -wall.Width/2, 0 )
    center2corner = FreeCAD.Rotation( FreeCAD.Vector(0,0,1), math.degrees(-angle) ).multVec(center2corner)

    corner = center.add(center2corner)
    pl = FreeCAD.Placement (
        corner, # translation
        FreeCAD.Rotation(math.degrees(-angle), 0 , 90 ),  # rotation
        FreeCAD.Vector( 0, 0, 0 ) # rotation@coordinate
    )

    # NOTE: the windows are not imported as meshes, but we use a simple
    #   correspondance between a catalog ID and a specific window preset from
    #   the parts library.
    catalog_id = imported_door.get('catalogId')
    if catalog_id in ("eTeks#fixedWindow85x123", "eTeks#window85x123", "eTeks#doubleWindow126x123", "eTeks#doubleWindow126x163", "eTeks#doubleFrenchWindow126x200", "eTeks#window85x163", "eTeks#frenchWindow85x200", "eTeks#doubleHungWindow80x122", "eTeks#roundWindow", "eTeks#halfRoundWindow"):
        windowtype = 'Open 2-pane'
    elif catalog_id in ("Scopia#window_2x1_with_sliders", "Scopia#window_2x3_arched", "Scopia#window_2x4_arched", "eTeks#sliderWindow126x200"):
        windowtype = 'Sliding 2-pane'
    elif catalog_id in ("eTeks#frontDoor", "eTeks#roundedDoor", "eTeks#door", "eTeks#doorFrame", "eTeks#roundDoorFrame"):
        windowtype = 'Simple door'
    else:
        FreeCAD.Console.PrintWarning(f"Unknown catalogId {catalog_id} for door {imported_door.get('id')}. Skipping\n")
        return None

    h1 = 10
    h2 = 10
    h3 = 0
    w1 = min(depth, wall.Width)
    w2 = 10
    o1 = 0
    o2 = w1 / 2
    window = Arch.makeWindowPreset(windowtype, width=width, height=height, h1=h1, h2=h2, h3=h3, w1=w1, w2=w2, o1=o1, o2=o2, placement=pl)
    window.Hosts = [wall]
    return window

def _get_wall(point):
    """Returns the wall that contains the given point.

    Args:
        point (FreeCAD.Vector): the point to test for

    Returns:
        Arch::Wall: the wall that contains the given point
    """
    for object in FreeCAD.ActiveDocument.Objects:
        if Draft.getType(object) == "Wall":
            bb = object.Shape.BoundBox
            FreeCAD.Console.PrintWarning(f"{object.id}: {object.Shape.BoundBox} / {point}\n")
            try:
                if bb.isInside(point):
                    return object
            except FloatingPointError:
                pass
    return None

def _import_furnitures(home, zip, floors):
    list(map(partial(_import_furniture, zip, floors), enumerate(home.findall('pieceOfFurniture'))))

def _import_furniture(zip, floors, imported_tuple):
    """Creates and returns a Mesh from the imported_furniture object

    Args:
        zip (ZipFile): the Zip containing the Mesh file
        floors (list): the list of imported levels
        imported_tuple (tuple): a tuple containing the index and the
            dict object containg the characteristics of the new object

    Returns:
        Mesh: the newly created object
    """
    (i, imported_furniture) = imported_tuple

    furniture = None
    if shoul_merge_elements:
        furniture = _get_element_to_merge(imported_furniture, 'pieceOfFurniture')

    if not furniture:
        # let's read the model first
        model = imported_furniture.get('model')
        if model not in zip.namelist():
            raise ValueError(f"Invalid SweetHome3D file: missing model {model}")
        materials = _import_materials(imported_furniture)
        mesh = _get_mesh_from_model(zip, model, materials)
        furniture = _create_furniture(floors, imported_furniture, mesh)
        FreeCAD.ActiveDocument.Furnitures.addObject(furniture)

        if "Material" not in furniture.PropertiesList and len(materials) > 0:
            furniture.addProperty(
                    "App::PropertyLink",
                    "Material",
                    "",
                    QT_TRANSLATE_NOOP(
                        "App::Property", "The Material for this object"
                    ),
            )
            furniture.Material = materials[0]

    #furniture.IfcType = "Furniture"

    _add_property(furniture, "App::PropertyString", "shType", "The element type")
    _add_furniture_common_attributes(furniture, imported_furniture)
    _add_piece_of_furniture_common_attributes(furniture, imported_furniture)
    _add_piece_of_furniture_horizontal_rotation_attributes(furniture, imported_furniture)

    furniture.shType = 'pieceOfFurniture'

    if i != 0 and i % 5 and FreeCAD.GuiUp:
        FreeCADGui.updateGui()

    return furniture

def _get_mesh_from_model(zip, model, materials):
    model_path_obj = None
    try:
        # Since mesh.read(model_data) does not work on BytesIO extract it first
        tmp_dir = FreeCAD.ActiveDocument.TransientDir
        if os.path.isdir(os.path.join(tmp_dir, model)):
            tmp_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
        model_path = zip.extract(member=model, path=tmp_dir)
        model_path_obj = model_path+".obj"
        os.rename(model_path, model_path_obj)
        mesh = Mesh.Mesh()
        mesh.read(model_path_obj)
    finally:
        if model_path_obj:
            os.remove(model_path_obj)
    return mesh

def _create_furniture(floors, imported_furniture, mesh):

    floor = _get_floor(floors, imported_furniture.get('level'))

    # REF: sweethome3d-code/SweetHome3D/src/com/eteks/sweethome3d/j3d/ModelManager.java:getPieceOfFurnitureNormalizedModelTransformation()
    width = _dim_sh2fc(float(imported_furniture.get('width')))
    depth = _dim_sh2fc(float(imported_furniture.get('depth')))
    height = _dim_sh2fc(float(imported_furniture.get('height')))
    x = float(imported_furniture.get('x',0))
    y = float(imported_furniture.get('y',0))
    z = float(imported_furniture.get('elevation', 0.0))
    angle = float(imported_furniture.get('angle', 0.0))
    name = imported_furniture.get('name')
    mirrored = bool(imported_furniture.get('modelMirrored', "false") == "true")

    # The meshes are normalized, facing up.
    # Center, Scale, X Rotation && Z Rotation (in FC axes), Move
    bb = mesh.BoundBox
    transform = FreeCAD.Matrix()
    transform.move(-bb.Center)
    # NOTE: the model is facing up, thus y and z are inverted
    transform.scale(width/bb.XLength, height/bb.YLength, depth/bb.ZLength)
    transform.rotateX(math.pi/2) # 90º
    transform.rotateZ(-angle)
    level_elevation = _dim_fc2sh(floor.Placement.Base.z)
    transform.move(_coord_sh2fc(FreeCAD.Vector(x, y, level_elevation + z + (_dim_fc2sh(height) / 2))))
    mesh.transform(transform)

    furniture = FreeCAD.ActiveDocument.addObject("Mesh::Feature", name)
    furniture.Mesh = mesh
    # return Arch.makeEquipment(baseobj=furniture, name=name)
    return furniture

def _add_furniture_common_attributes(furniture, imported_furniture):
    _add_property(furniture, "App::PropertyString", "id", "The furniture's id")
    _add_property(furniture, "App::PropertyFloat", "angle", "The angle of the furniture")
    _add_property(furniture, "App::PropertyBool", "visible", "Whether the object is visible")
    _add_property(furniture, "App::PropertyBool", "movable", "Whether the object is movable")
    _add_property(furniture, "App::PropertyString", "description", "The object's description")
    _add_property(furniture, "App::PropertyString", "information", "The object's information")
    _add_property(furniture, "App::PropertyString", "license", "The object's license")
    _add_property(furniture, "App::PropertyString", "creator", "The object's creator")
    _add_property(furniture, "App::PropertyBool", "modelMirrored", "Whether the object is mirrored")
    _add_property(furniture, "App::PropertyBool", "nameVisible", "Whether the object's name is visible")
    _add_property(furniture, "App::PropertyFloat", "nameAngle", "The object's name angle")
    _add_property(furniture, "App::PropertyFloat", "nameXOffset", "The object's name X offset")
    _add_property(furniture, "App::PropertyFloat", "nameYOffset", "The object's name Y offset")
    _add_property(furniture, "App::PropertyFloat", "price", "The object's price")

    furniture.id = str(imported_furniture.get('id'))
    furniture.angle = float(imported_furniture.get('angle', 0))
    furniture.visible = bool(imported_furniture.get('visible', True))
    furniture.movable = bool(imported_furniture.get('movable', True))
    furniture.description = str(imported_furniture.get('description', ''))
    furniture.information = str(imported_furniture.get('information', ''))
    furniture.license = str(imported_furniture.get('license', ''))
    furniture.creator = str(imported_furniture.get('creator', ''))
    furniture.modelMirrored = bool(imported_furniture.get('modelMirrored', False))
    furniture.nameVisible = bool(imported_furniture.get('nameVisible', False))
    furniture.nameAngle = float(imported_furniture.get('nameAngle', 0))
    furniture.nameXOffset = float(imported_furniture.get('nameXOffset', 0))
    furniture.nameYOffset = float(imported_furniture.get('nameYOffset', 0))
    furniture.price = float(imported_furniture.get('price', 0))

def _add_piece_of_furniture_common_attributes(furniture, imported_furniture):
    _add_property(furniture, "App::PropertyString", "level", "The furniture's level")
    _add_property(furniture, "App::PropertyString", "catalogId", "The furniture's catalog id")
    _add_property(furniture, "App::PropertyFloat", "dropOnTopElevation", "")
    _add_property(furniture, "App::PropertyString", "model", "The object's mesh file")
    _add_property(furniture, "App::PropertyString", "icon", "The object's icon")
    _add_property(furniture, "App::PropertyString", "planIcon", "The object's icon for the plan view")
    _add_property(furniture, "App::PropertyString", "modelRotation", "The object's model rotation")
    _add_property(furniture, "App::PropertyString", "modelCenteredAtOrigin", "The object's center")
    _add_property(furniture, "App::PropertyBool", "backFaceShown", "Whether the object's back face is shown")
    _add_property(furniture, "App::PropertyString", "modelFlags", "The object's flags")
    _add_property(furniture, "App::PropertyFloat", "modelSize", "The object's size")
    _add_property(furniture, "App::PropertyBool", "doorOrWindow", "Whether the object is a door or Window")
    _add_property(furniture, "App::PropertyBool", "resizable", "Whether the object is resizable")
    _add_property(furniture, "App::PropertyBool", "deformable", "Whether the object is deformable")
    _add_property(furniture, "App::PropertyBool", "texturable", "Whether the object is texturable")
    _add_property(furniture, "App::PropertyString", "staircaseCutOutShape", "")
    _add_property(furniture, "App::PropertyFloat", "shininess", "The object's shininess")
    _add_property(furniture, "App::PropertyFloat", "valueAddedTaxPercentage", "The object's VAT percentage")
    _add_property(furniture, "App::PropertyString", "currency", "The object's price currency")

    furniture.level = str(imported_furniture.get('level', ''))
    furniture.catalogId = str(imported_furniture.get('catalogId', ''))
    furniture.dropOnTopElevation = float(imported_furniture.get('dropOnTopElevation', 0))
    furniture.model = str(imported_furniture.get('model', ''))
    furniture.icon = str(imported_furniture.get('icon', ''))
    furniture.planIcon = str(imported_furniture.get('planIcon', ''))
    furniture.modelRotation = str(imported_furniture.get('modelRotation', ''))
    furniture.modelCenteredAtOrigin = str(imported_furniture.get('modelCenteredAtOrigin', ''))
    furniture.backFaceShown = bool(imported_furniture.get('backFaceShown', False))
    furniture.modelFlags = str(imported_furniture.get('modelFlags', ''))
    furniture.modelSize = float(imported_furniture.get('modelSize', 0))
    furniture.doorOrWindow = bool(imported_furniture.get('doorOrWindow', False))
    furniture.resizable = bool(imported_furniture.get('resizable', True))
    furniture.deformable = bool(imported_furniture.get('deformable', True))
    furniture.texturable = bool(imported_furniture.get('texturable', True))
    furniture.staircaseCutOutShape = str(imported_furniture.get('staircaseCutOutShape', ''))
    furniture.shininess = float(imported_furniture.get('shininess', 0))
    furniture.valueAddedTaxPercentage = float(imported_furniture.get('valueAddedTaxPercentage', 0))
    furniture.currency = str(imported_furniture.get('currency', 'EUR'))

def _add_piece_of_furniture_horizontal_rotation_attributes(furniture, imported_furniture):
    _add_property(furniture, "App::PropertyBool", "horizontallyRotatable", "Whether the object horizontally rotatable")
    _add_property(furniture, "App::PropertyFloat", "pitch", "The object's pitch")
    _add_property(furniture, "App::PropertyFloat", "roll", "The object's roll")
    _add_property(furniture, "App::PropertyFloat", "widthInPlan", "The object's width in the plan view")
    _add_property(furniture, "App::PropertyFloat", "depthInPlan", "The object's depth in the plan view")
    _add_property(furniture, "App::PropertyFloat", "heightInPlan", "The object's height in the plan view")

    furniture.horizontallyRotatable = bool(imported_furniture.get('horizontallyRotatable', True))
    furniture.pitch = float(imported_furniture.get('pitch', 0))
    furniture.roll = float(imported_furniture.get('roll', 0))
    furniture.widthInPlan = float(imported_furniture.get('widthInPlan', 0))
    furniture.depthInPlan = float(imported_furniture.get('depthInPlan', 0))
    furniture.heightInPlan = float(imported_furniture.get('heightInPlan', 0))

def _import_materials(imported_furniture):
    if 'material' not in imported_furniture:
        return []

    imported_materials = imported_furniture.findall('material')
    materials = []
    try:
        for imported_material in imported_materials:
            name = imported_material.get('name')
            color = imported_material.get('color', 'FF000000')
            shininess = imported_material.get('shininess', '0.0')
            material = Arch.makeMaterial(
                name=name,
                color=_hex2rgb(color),
                transparency=_hex2transparency(color)
                )
            _add_property(material, "App::PropertyFloat", "shininess", "The shininess of the material")
            material.shininess = float(shininess)
            materials.append(material)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Error while creating material {e}")

    return materials

def _import_lights(home, zip, floors):
    list(map(partial(_import_light, zip, floors), enumerate(home.findall('light'))))

def _import_light(zip, floors, imported_tuple):
    """Creates and returns a Render light from the imported_light object

    Args:
        zip (ZipFile): the Zip containing the Mesh file
        floors (list): the list of imported levels
        imported_tuple (tuple): a tuple containing the index and the
            dict object containg the characteristics of the new object

    Returns:
        Mesh: the newly created object
    """
    light_appliance = _import_furniture(zip, floors, imported_tuple)

    (i, imported_light) = imported_tuple

    _add_property(light_appliance, "App::PropertyFloat", "power", "The power of the light")
    light_appliance.power = float(imported_light.get('power', 0.5))

    if i != 0 and i % 5 and FreeCAD.GuiUp:
        FreeCADGui.updateGui()

    if not RENDER_AVAILABLE:
        return None

    for j,light_source in enumerate(imported_light.findall('lightSource')):
        x = float(light_source.get('x'))
        y = float(light_source.get('y'))
        z = float(light_source.get('z'))
        diameter = float(light_source.get('diameter'))
        color = light_source.get('color')

        light_source_id = f"{imported_light.get('id')}-{j}"
        feature = None
        if shoul_merge_elements:
            feature = _get_element_to_merge({'id':light_source_id}, 'lightSource')

        if not feature:
            _, feature, _ = Render.PointLight.create()

        feature.Label = light_appliance.Label
        feature.Placement.Base = _coord_sh2fc(FreeCAD.Vector(x,y,z))
        feature.Radius = _dim_sh2fc(diameter / 2)
        feature.Color = _hex2rgb(color)
        FreeCAD.ActiveDocument.Lights.addObject(feature)

        _add_property(feature, "App::PropertyString", "shType", "The element type")
        _add_property(feature, "App::PropertyString", "id", "The elment's id")

        feature.shType = 'lightSource'
        feature.id = light_source_id

    return feature

def _import_observer_cameras(home):
    if not RENDER_AVAILABLE:
        return []
    return list(map(partial(_import_observer_camera), enumerate(home.findall('observerCamera'))))

def _import_observer_camera(imported_tuple):
    """Creates and returns a Render Camera from the imported_camera object

    Args:
        zip (ZipFile): the Zip containing the Mesh file
        floors (list): the list of imported levels
        imported_tuple (tuple): a tuple containing the index and the
            dict object containg the characteristics of the new object

    Returns:
        Mesh: the newly created object
    """
    (i, imported_camera) = imported_tuple

    x = float(imported_camera.get('x'))
    y = float(imported_camera.get('y'))
    z = float(imported_camera.get('z'))
    yaw = float(imported_camera.get('yaw'))
    pitch = float(imported_camera.get('pitch'))
    # ¿How to convert fov to FocalLength?
    fieldOfView = float(imported_camera.get('fieldOfView'))

    camera_id = f"observerCamera-{i}"
    feature = None
    if shoul_merge_elements:
        feature = _get_element_to_merge({'id':camera_id}, 'observerCamera')

    if not feature:
        _, feature, _ = Render.Camera.create()
        FreeCAD.ActiveDocument.Cameras.addObject(feature)

    feature.Label = imported_camera.get('name', 'ObserverCamera')
    feature.Placement.Base = _coord_sh2fc(FreeCAD.Vector(x,y,z))
    # NOTE: the coordinate system is screen like, thus roll & picth are inverted ZY'X''
    feature.Placement.Rotation.setYawPitchRoll(math.degrees(yaw), math.degrees(pitch), 0)
    feature.Projection = "Perspective"
    feature.AspectRatio = 1.33333333 # /home/environment/@photoAspectRatio

    _add_property(feature, "App::PropertyString", "shType", "The element type")
    _add_property(feature, "App::PropertyEnumeration", "attribute", "The type of camera")
    _add_property(feature, "App::PropertyBool", "fixedSize", "Whether the object is fixed size")
    _add_camera_common_attributes(feature, imported_camera)

    feature.shType = 'observerCamera'
    feature.id = camera_id
    feature.attribute = ["observerCamera", "storedCamera", "cameraPath"]
    feature.attribute = imported_camera.get('attribute')
    feature.fixedSize = bool(imported_camera.get('fixedSize', False))

    if i != 0 and i % 5 and FreeCAD.GuiUp:
        FreeCADGui.updateGui()

    return feature

def _add_camera_common_attributes(feature, imported_camera):
    _add_property(feature, "App::PropertyString", "id", "The object horizontally rotatable")
    _add_property(feature, "App::PropertyEnumeration", "lens", "The object's lens (PINHOLE | NORMAL | FISHEYE | SPHERICAL)")
    _add_property(feature, "App::PropertyFloat", "yaw", "The object's roll")
    _add_property(feature, "App::PropertyFloat", "pitch", "The object's width in the plan view")
    _add_property(feature, "App::PropertyFloat", "time", "The object's depth in the plan view")
    _add_property(feature, "App::PropertyFloat", "fieldOfView", "The object's height in the plan view")
    _add_property(feature, "App::PropertyString", "renderer", "The object's height in the plan view")

    feature.id = str(imported_camera.get('id', True))
    feature.lens = ["PINHOLE", "NORMAL", "FISHEYE", "SPHERICAL"]
    feature.lens = str(imported_camera.get('lens', "PINHOLE"))
    feature.yaw = float(imported_camera.get('yaw'))
    feature.pitch = float(imported_camera.get('pitch'))
    feature.time = float(imported_camera.get('time', 0))
    feature.fieldOfView = float(imported_camera.get('fieldOfView'))
    feature.renderer = str(imported_camera.get('renderer', ''))

def _rgb2hex(r,g,b):
    return "{:02x}{:02x}{:02x}".format(r,g,b)

def _hex2rgb(hexcode):
    # We might have transparency as the first 2 digit
    offset = 0 if len(hexcode) == 6 else 2
    return (int(hexcode[offset:offset+2], 16),   # Red
            int(hexcode[offset+2:offset+4], 16), # Green
            int(hexcode[offset+4:offset+6], 16)  # Blue
            )

def _hex2transparency(hexcode):
    return 50 if DEBUG else 100 - int( int(hexcode[0:2], 16) * 100 / 255 )

def _set_color_and_transparency(obj, color):
    if not FreeCAD.GuiUp or not color:
        return
    if hasattr(obj.ViewObject,"ShapeColor"):
        obj.ViewObject.ShapeColor = _hex2rgb(color)
    if hasattr(obj.ViewObject,"Transparency"):
        obj.ViewObject.Transparency = _hex2transparency(color)

def _get_sh3d_property(home, property_name, default_value=None):
    """Return a SweetHome3D <property> element whith the specified name

    Args:
        home (ElementTree): the root of the SweetHome3D XML file
        property_name (str): the property name to lookup
        default_value (any): the property default value

    Returns:
        str: the value of said property or None if it does not exists
    """
    for property in home.findall('property'):
        if property.get('name') == property_name:
            return property.get('value')
    return default_value

def _coord_fc2sh(vector):
    """Converts FreeCAD to SweetHome coordinate

    Args:
        FreeCAD.Vector (FreeCAD.Vector): The coordinate in FreeCAD

    Returns:
        FreeCAD.Vector: the SweetHome coordinate
    """
    return FreeCAD.Vector(vector.x/FACTOR, -vector.y/FACTOR, vector.z/FACTOR)

def _coord_sh2fc(vector):
    """Converts SweetHome to FreeCAD coordinate

    Args:
        FreeCAD.Vector (FreeCAD.Vector): The coordinate in SweetHome

    Returns:
        FreeCAD.Vector: the FreeCAD coordinate
    """
    return FreeCAD.Vector(vector.x*FACTOR, -vector.y*FACTOR, vector.z*FACTOR)

def _dim_fc2sh(dimension):
    """Convert FreeCAD dimension (mm) to SweetHome dimension (cm)

    Args:
        dimension (float): The dimension in FreeCAD

    Returns:
        float: the SweetHome dimension
    """
    return float(dimension)/FACTOR

def _dim_sh2fc(dimension):
    """Convert SweetHome dimension (cm) to FreeCAD dimension (mm)

    Args:
        dimension (float): The dimension in SweetHome

    Returns:
        float: the FreeCAD dimension
    """
    return float(dimension)*FACTOR

def _ang_sh2fc(angle):
    """Convert SweetHome angle (º) to FreeCAD angle (º)

    SweetHome angles are clockwise positive while FreeCAD are anti-clockwise 
    positive

    Args:
        angle (float): The angle in SweetHome

    Returns:
        float: the FreeCAD angle
    """
    return -float(angle)

def _ang_fc2sh(angle):
    """Convert FreeCAD angle (º) to SweetHome angle (º)

    SweetHome angles are clockwise positive while FreeCAD are anti-clockwise 
    positive

    Args:
        angle (float): The angle in FreeCAD

    Returns:
        float: the SweetHome angle
    """
    return -float(angle)

def _add_property(obj, property_type, name, description):
    if name not in obj.PropertiesList:
        obj.addProperty(property_type, name, "SweetHome3D", description)

def _get_element_to_merge(imported_element, sh_type=None):
    global shoul_merge_elements
    global document_elements
    id = imported_element.get('id')
    if shoul_merge_elements and id in document_elements:
        element = document_elements[id]
        if sh_type:
            assert element.shType == sh_type, f"Invalid shType: expected {sh_type}, got {element.shType}"
        if DEBUG:
            FreeCAD.Console.PrintMessage(f"Merging imported element '{id}' with existing element of type '{type(element)}'\n")
        return element
    if DEBUG:
        FreeCAD.Console.PrintMessage(f"No element found with id '{id}' and type '{sh_type}'\n")

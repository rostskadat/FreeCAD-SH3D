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

from zipfile import ZipFile
from sh3d import import_observer_cameras, import_furnitures, import_lights#, import_rooms, import_walls
from sh3d.utils import get_default_placement, get_property, coord_sh2fc, dim_sh2fc, hex2rgb, add_property, get_attr, set_color_and_transparency,dim_fc2sh, FACTOR
import Arch, Draft, Mesh
from DraftVecUtils import angle
from functools import partial
from math import degrees, sqrt, pi, atan
import uuid
#from lxml import etree

import FreeCAD as App
import os, Arch, xmltodict

if App.GuiUp:
    from draftutils.translate import translate
else:
    # \cond
    def translate(context,text):
        return text
    # \endcond

## @package importSH3D
#  \ingroup ARCH
#  \brief SweetHome3D file format importer and exporter
#
#  This module provides tools to import and export SweetHome3D (.sh3d) files.

__title__  = "FreeCAD SweetHome3D importer"
__author__ = "Julien Masnada"
__url__    = "https://www.freecad.org"

# CF: schema.dtd
LIST_ELEMENTS = ('material', 'baseboard', 'property', 'furnitureVisibleProperty', 'camera', 'observerCamera', 'level', 'pieceOfFurniture', 'doorOrWindow', 'furnitureGroup', 'light', 'wall', 'room', 'polyline', 'dimensionLine', 'label')

DEBUG = True

try:
    # Python 2 forward compatibility
    range = xrange
except NameError:
    pass

def checkSH3D():
    return True


def open(filename):
    "called when freecad wants to open a file"
    if not checkSH3D():
        return
    docname = os.path.splitext(os.path.basename(filename))[0]
    doc = App.newDocument(docname)
    doc.Label = docname
    App.ActiveDocument = doc
    read(filename)
    return doc


def insert(filename,docname):
    "called when freecad wants to import a file"
    if not checkSH3D():
        return
    try:
        doc = App.getDocument(docname)
    except NameError:
        doc = App.newDocument(docname)
    App.ActiveDocument = doc
    read(filename)
    return doc

def import_level(imported_level):
    floor = Arch.makeFloor()
    floor.Label = imported_level['@name']
    floor.Placement.Base.z = dim_sh2fc(float(imported_level['@elevation']))

    add_property(floor, "App::PropertyString", "id", "The floor's id")
    add_property(floor, "App::PropertyFloat", "floorThickness", "The floor's slab thickness")
    add_property(floor, "App::PropertyFloat", "height", "The room's height")
    add_property(floor, "App::PropertyInteger", "elevationIndex", "The floor number")
    add_property(floor, "App::PropertyBool", "viewable", "Whether the floor is viewable")

    floor.id             = imported_level['@id']
    floor.floorThickness = dim_sh2fc(float(imported_level['@floorThickness']))
    floor.height         = dim_sh2fc(float(imported_level['@height']))
    floor.elevationIndex = int(get_attr(imported_level, '@elevationIndex', 0))
    floor.ViewObject.Visibility = get_attr(imported_level, '@visible', 'false') == 'true'

    return floor

def import_levels(home):
    """Import all the level found in the file

    It will create a list of level, (or BIM Floor).

    Args:
        home (xml): The home to be imported

    Returns:
        list: the list of imported floors
    """
    return list(map(import_level, home['home']['level']))

def get_floor(floors, level_id):
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

def import_room(floors, imported_room):
    floor = get_floor(floors, get_attr(imported_room, '@level', None))

    pl = get_default_placement()
    points = []
    for point in imported_room['point']:
        x = float(point['@x'])
        y = float(point['@y'])
        z = dim_fc2sh(floor.Placement.Base.z)
        points.append(coord_sh2fc(App.Vector(x, y, z)))
    line = Draft.make_wire(points, placement=pl, closed=True, face=True, support=None)
    slab = Arch.makeStructure(line, height=floor.floorThickness)
    slab.Label = get_attr(imported_room, '@name', 'Room')
    slab.IfcType = "Slab"
    slab.Normal = App.Vector(0,0,-1)
    if App.GuiUp:
      set_color_and_transparency(slab, get_attr(imported_room, '@floorColor', 'FF96A9BA'))
      # ceilingColor is not imported in the model as it depends on the upper room

    add_property(slab, "App::PropertyString", "id", "The slab's id")
    add_property(slab, "App::PropertyFloat", "nameAngle", "The room's name angle")
    add_property(slab, "App::PropertyFloat", "nameXOffset", "The room's name x offset")
    add_property(slab, "App::PropertyFloat", "nameYOffset", "The room's name y offset")
    add_property(slab, "App::PropertyBool", "areaVisible", "Whether the area of the room is displayed in the plan view")
    add_property(slab, "App::PropertyFloat", "areaAngle", "The room's area annotation angle")
    add_property(slab, "App::PropertyFloat", "areaXOffset", "The room's area annotation x offset")
    add_property(slab, "App::PropertyFloat", "areaYOffset", "The room's area annotation y offset")
    add_property(slab, "App::PropertyBool", "floorVisible", "Whether the floor of the room is displayed")
    add_property(slab, "App::PropertyString", "floorColor", "The room's floor color")
    add_property(slab, "App::PropertyFloat", "floorShininess", "The room's floor shininess")
    add_property(slab, "App::PropertyBool", "ceilingVisible", "Whether the ceiling of the room is displayed")
    add_property(slab, "App::PropertyString", "ceilingColor", "The room's ceiling color")
    add_property(slab, "App::PropertyFloat", "ceilingShininess", "The room's ceiling shininess")
    add_property(slab, "App::PropertyBool", "ceilingFlat", "")

    slab.id = get_attr(imported_room, '@id', str(uuid.uuid4()))
    slab.nameAngle = float(get_attr(imported_room, '@nameAngle', 0))
    slab.nameXOffset = float(get_attr(imported_room, '@nameXOffset', 0))
    slab.nameYOffset = float(get_attr(imported_room, '@nameYOffset', -400))
    slab.areaVisible = bool(get_attr(imported_room, '@areaVisible', False))
    slab.areaAngle = float(get_attr(imported_room, '@areaAngle', 0))
    slab.areaXOffset = float(get_attr(imported_room, '@areaXOffset', 0))
    slab.areaYOffset = float(get_attr(imported_room, '@areaYOffset', 0))
    slab.floorVisible = bool(get_attr(imported_room, '@floorVisible', True))
    slab.floorColor = str(get_attr(imported_room, '@floorColor', 'FF96A9BA'))
    slab.floorShininess = float(get_attr(imported_room, '@floorShininess', 0))
    slab.ceilingVisible = bool(get_attr(imported_room, '@ceilingVisible', True))
    slab.ceilingColor = str(get_attr(imported_room, '@ceilingColor', 'FF000000'))
    slab.ceilingShininess = float(get_attr(imported_room, '@ceilingShininess', 0))
    slab.ceilingFlat = bool(get_attr(imported_room, '@ceilingFlat', False))

    floor.addObject(slab)
    return slab

def import_rooms(home, floors):
    """Import all the rooms found in the file

    It will create a list of rooms, (or BIM Slab).

    Args:
        home (xml): The home to be imported
        floors (list): The list of floor each room references

    Returns:
        list: the list of imported rooms
    """
    return list(map(partial(import_room, floors), home['home']['room']))

def add_colored_side(solid, face, color, side):
    facebinder = Draft.make_facebinder([(solid, (face))], name=f"{solid.Label} {side}")
    facebinder.Extrusion = 1.0
    set_color_and_transparency(facebinder, color)
    return facebinder

def add_colored_sides(imported_solid, solid):
    """Add a FaceBinder on either side of the solid.

    When the imported solid has the leftSideColor/rightSideColor attribute set,
    we create a facebinder on each side in order to set the corresponding 
    color.

    Args:
        imported_solid (dict): the wall that is to be imported
        solid (Part): the wall to be constructued

    Returns:
        list: The list of facebinders
    """
    # The left side is defined as the face on the left hand side when going
    # from (xStart,yStart) to (xEnd,yEnd). Namely Face1 (Left) and 
    # Face3 (Right)
    facebinders = []
    # The solid is a wall
    if '@leftSideColor' in imported_solid:
        facebinders.append(add_colored_side(solid, "Face1", imported_solid['@leftSideColor'], "leftSide"))
    if '@rightSideColor' in imported_solid:
        facebinders.append(add_colored_side(solid, "Face3", imported_solid['@rightSideColor'], "rightSide"))
    return facebinders

def import_baseboard(wall, has_facebinders, imported_baseboard):
    wall_width = float(wall.Width)
    baseboard_width = dim_sh2fc(imported_baseboard['@thickness'])
    baseboard_height = dim_sh2fc(imported_baseboard['@height'])
    vertexes = wall.Shape.Vertexes

    # The left side is defined as the face on the left hand side when going
    # from (xStart,yStart) to (xEnd,yEnd). I assume the points are always 
    # created in the same order. We then have on the lefthand side the points
    # 1 and 2, while on the righthand side we have the points 4 and 6
    side = imported_baseboard['@attribute']
    facebinder_width = 0
    if side == 'leftSideBaseboard':
        p_start = vertexes[0].Point
        p_end = vertexes[2].Point
        p_normal = vertexes[4].Point
        if has_facebinders['left']:
            facebinder_width = 1
    if side == 'rightSideBaseboard':
        p_start = vertexes[4].Point
        p_end = vertexes[6].Point
        p_normal = vertexes[0].Point
        if has_facebinders['right']:
            facebinder_width = 1

    v_normal = p_normal - p_start
    v_facebinder = v_normal * (facebinder_width/wall_width)
    v_baseboard = v_normal * (baseboard_width/wall_width)
    p0 = p_start - v_facebinder
    p1 = p_end - v_facebinder
    p2 = p_end - v_facebinder - v_baseboard
    p3 = p_start - v_facebinder - v_baseboard

    # I first add a rectangle
    baseboard_base = Draft.make_rectangle([p0, p1, p2, p3], face=True, support=None)

    # and then I extrude
    baseboard = App.ActiveDocument.addObject('Part::Extrusion', f"{wall.Label} {side}")
    baseboard.Base = baseboard_base
    baseboard.DirMode = "Custom"
    baseboard.Dir = App.Vector(0, 0, 1)
    baseboard.DirLink = None
    baseboard.LengthFwd = baseboard_height
    baseboard.LengthRev = 0
    baseboard.Solid = True
    baseboard.Reversed = False
    baseboard.Symmetric = False
    baseboard.TaperAngle = 0
    baseboard.TaperAngleRev = 0
    baseboard_base.Visibility = False

    if App.GuiUp:
        if '@color' in imported_baseboard:
            set_color_and_transparency(baseboard, imported_baseboard['@color'])
    return baseboard

def import_baseboards(imported_wall, wall):
    baseboards = []
    if 'baseboard' in imported_wall:
        obj = imported_wall['baseboard']
        # If there is just one baseboard it appears as a dict, not a list
        if type(obj) == type(dict()):
            baseboards.append(obj)
        else:
            baseboards.extend(obj)
    has_facebinders = {'left':False,'right':False}
    if '@leftSideColor' in imported_wall:
        has_facebinders['left'] = True
    if '@rightSideColor' in imported_wall:
        has_facebinders['right'] = True
    return list(map(partial(import_baseboard, wall, has_facebinders), baseboards))

def _make_straight_wall(floor, imported_wall):
    x_start = float(imported_wall['@xStart'])
    y_start = float(imported_wall['@yStart'])
    z_start = dim_fc2sh(floor.Placement.Base.z)
    x_end = float(imported_wall['@xEnd'])
    y_end = float(imported_wall['@yEnd'])

    pl = get_default_placement()
    points = [
        coord_sh2fc(App.Vector(x_start, y_start, z_start)), 
        coord_sh2fc(App.Vector(x_end, y_end, z_start))
    ]
    line = Draft.make_wire(points, placement=pl, closed=False, face=True, support=None)
    wall = Arch.makeWall(line)
    wall.Height = dim_sh2fc(float(get_attr(imported_wall, '@height', dim_fc2sh(floor.height))))
    wall.Width = dim_sh2fc(float(imported_wall['@thickness']))
    wall.Normal = App.Vector(0, 0, 1)
    return wall

def _make_tappered_wall(floor, imported_wall):

    name = imported_wall['@id']

    # in SH coord
    x_start = float(imported_wall['@xStart'])
    y_start = float(imported_wall['@yStart'])
    z_start = dim_fc2sh(floor.Placement.Base.z)
    v_start = App.Vector(x_start, y_start, z_start)

    x_end = float(imported_wall['@xEnd'])
    y_end = float(imported_wall['@yEnd'])
    v_end = App.Vector(x_end, y_end, z_start)

    v_length = v_end - v_start
    v_center = v_start + v_length / 2
    length = v_start.distanceToPoint(v_end)

    thickness = float(imported_wall['@thickness'])

    height = float(get_attr(imported_wall, '@height', dim_fc2sh(floor.height)))
    height_at_end = float(get_attr(imported_wall, '@heightAtEnd', height))

    # NOTE: App.Vector.getAngle return unsigned angle, using 
    #   DraftVecUtils.angle instead
    phi = angle(App.Vector(1,0,0), v_center)
    theta = angle(v_center, v_length)

    # in FC coordinate
    mesh = Mesh.createBox(1,1,1)
    scale = coord_sh2fc(App.Vector(length, thickness, height))
    transform = App.Matrix()
    transform.move(App.Vector(0,0,0.5)) # bring the box up a notch
    #print(f"scale({name})={scale}")
    transform.scale(scale)
    print(f"rotateZ({name})= {degrees(theta)}+{degrees(theta)} => {degrees(phi+theta)}")
    transform.rotateZ(phi+theta)
    #print(f"move({name})={coord_sh2fc(v_center)}")
    transform.move(coord_sh2fc(v_center))
    mesh.transform(transform)

    mesh.movePoint(2, coord_sh2fc(App.Vector(0,0,height_at_end-height)))
    mesh.movePoint(5, coord_sh2fc(App.Vector(0,0,height_at_end-height)))

    feature = App.ActiveDocument.addObject("Mesh::Feature", "Mesh")
    feature.Mesh = mesh
    wall = Arch.makeWall(feature)
    return wall

def _make_arqued_wall(floor, imported_wall):
    return _make_straight_wall(floor, imported_wall)

def import_wall(floors, facebinder_group, baseboard_group, imported_wall):
    
    floor = get_floor(floors, get_attr(imported_wall, '@level', None))

    if '@heightAtEnd' in imported_wall:
        wall = _make_tappered_wall(floor, imported_wall)
    elif '@arcExtent' in imported_wall:
        wall = _make_arqued_wall(floor, imported_wall)
    else:
        wall = _make_straight_wall(floor, imported_wall)

    wall.Label = imported_wall['@id']
    if App.GuiUp:
        set_color_and_transparency(wall, get_attr(imported_wall, '@topColor', 'FF96A9BA'))

    App.ActiveDocument.recompute()
    if facebinder_group:
        facebinders = add_colored_sides(imported_wall, wall)
        if len(facebinders):
            facebinder_group.addObjects(facebinders)
    if baseboard_group:
        baseboards = import_baseboards(imported_wall, wall)
        if len(baseboards):
            baseboard_group.addObjects(baseboards)

    add_property(wall, "App::PropertyString", "id", "The wall's id")
    add_property(wall, "App::PropertyString", "wallAtStart", "The Id of the contiguous wall at the start of this wall")
    add_property(wall, "App::PropertyString", "wallAtEnd", "The Id of the contiguous wall at the end of this wall")
    add_property(wall, "App::PropertyString", "pattern", "The pattern of this wall in plan view")
    add_property(wall, "App::PropertyFloat", "leftSideShininess", "The wall's left hand side shininess")
    add_property(wall, "App::PropertyFloat", "rightSideShininess", "The wall's right hand side shininess")

    wall.wallAtStart = get_attr(imported_wall, '@wallAtStart', '')
    wall.wallAtEnd = get_attr(imported_wall, '@wallAtEnd', '')
    wall.pattern = get_attr(imported_wall, '@pattern', '')
    wall.leftSideShininess = float(get_attr(imported_wall, '@leftSideShininess', 0))
    wall.rightSideShininess = float(get_attr(imported_wall, '@rightSideShininess', 0))

    floor.addObject(wall)
    return wall

def import_walls(home, floors, facebinder_group, baseboard_group):
    """Returns the list of imported walls

    Args:
        home (xml): The home to be imported
        floors (list): The list of floor each wall references
        facebinder_group (App::DocumentObjectGroup): The group where the faceBinder will be added
        baseboard_group (App::DocumentObjectGroup): The group where the baseboard will be added

    Returns:
        list: the list of imported walls
    """
    return list(map(partial(import_wall, floors, facebinder_group, baseboard_group), home['home']['wall'][0:]))

def read(filename):
    "reads a SH3D file"

    # TODO: Should load the preferences, such as default slab thickness, or
    #   whether to create default project / site and building. The IFC export
    #   should be a good starting point.
    p = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Arch")
    default_ = p.GetInt("ColladaMesher",0)

    if not App.ActiveDocument:
        App.Console.PrintError("No active document. Aborting\n")
        return None

    with ZipFile(filename, 'r') as zip:
        entries = zip.namelist()
        if "Home.xml" not in entries:
            raise ValueError("Invalid SweetHome3D file: missing Home.xml")
        home = xmltodict.parse(zip.read("Home.xml"), force_list=LIST_ELEMENTS)

        if 'level' in home['home']:
            floors = import_levels(home)
        else:
            floors = [Arch.makeFloor()]

        import_rooms(home, floors)

        facebinder_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Facebinders")
        baseboard_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Baseboards")
        light_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Lights")
        camera_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Cameras")

        import_walls(home, floors, facebinder_group, baseboard_group)
        # furniture_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Furnitures")
        # furnitures = import_furnitures(home, zip, furniture_group)
        # lights = import_lights(home, zip, furniture_group, light_group)
        # cameras = import_observer_cameras(home, camera_group)

        building = Arch.makeBuilding(floors)
        #building.Label = home['home']['label']['text']
        site = Arch.makeSite([ building ])
        project = Arch.makeProject([ ])

        # TODO: Should be set only when opening a file, not when importing
        App.ActiveDocument.Label = building.Label
        App.ActiveDocument.CreatedBy = get_property(home, 'Author')
        App.ActiveDocument.Comment = get_property(home, 'Copyright')
        App.ActiveDocument.License = get_property(home, 'License')

    App.ActiveDocument.recompute()
    return home


def export(exportList,filename,tessellation=1,colors=None):
    # REF: /home/rostskadat/git/opensource/sweethome3d-code/sweethome3d-code/SweetHome3D/src/com/eteks/sweethome3d/io/HomeFileRecorder.java
    # Creating a zip file with 2 entries (Home, and Home.xml
    if not checkSH3D():
        return
    App.Console.PrintMessage(translate("Arch","file %s successfully created.") % filename)

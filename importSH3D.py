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

import FreeCAD as App
import FreeCADGui as Gui
import Arch, Draft, Mesh, WorkingPlane
import uuid, xmltodict

from DraftVecUtils import angle
from functools import partial
from math import degrees, pi
from os import rename, remove
from os.path import join, isdir
from PySide.QtCore import QT_TRANSLATE_NOOP
from zipfile import ZipFile

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
LIST_ELEMENTS = ('material', 'baseboard', 'property', 'furnitureVisibleProperty', 'camera', 'observerCamera', 'level', 'pieceOfFurniture', 'doorOrWindow', 'furnitureGroup', 'light', 'wall', 'room', 'polyline', 'dimensionLine', 'label', 'doorOrWindow')
PART_LIBRARY_PATH = "/home/rostskadat/snap/freecad/common/Mod/parts_library"
# SweetHome3D is in cm while FreeCAD is in mm
FACTOR = 10

DEBUG = False

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

def read(filename):
    """Reads a SweetHome 3D file and import it into FreeCAD

    Args:
        filename (str): the name of the SweetHome 3D file to import

    Raises:
        ValueError: raised if the file is corrupted

    """

    # TODO: Should load the preferences, such as default slab thickness, or
    #   whether to create default project / site and building. The IFC export
    #   should be a good starting point.
    p = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Arch")
    default_ = p.GetInt("ColladaMesher",0)

    if not App.ActiveDocument:
        App.Console.PrintError("No active document. Aborting\n")
        return

    with ZipFile(filename, 'r') as zip:
        entries = zip.namelist()
        if "Home.xml" not in entries:
            raise ValueError("Invalid SweetHome3D file: missing Home.xml")
        home = xmltodict.parse(zip.read("Home.xml"), force_list=LIST_ELEMENTS)

        document = App.ActiveDocument
        document.addObject("App::DocumentObjectGroup","Baseboards")
        document.addObject("App::DocumentObjectGroup","Cameras")
        document.addObject("App::DocumentObjectGroup","Furnitures")
        document.addObject("App::DocumentObjectGroup","Lights")

        if 'level' in home['home']:
            floors = import_levels(home)
        else:
            floors = [create_default_floor()]

        import_rooms(home, floors)
        import_walls(home, floors)
        import_doors(home, floors)
        import_furnitures(home, zip, floors)
        #import_lights(home, zip, floors)
        #import_observer_cameras(home)

        building = Arch.makeBuilding(floors)
        #building.Label = home['home']['label']['text']
        Arch.makeSite([ building ])
        Arch.makeProject([ ])

        # TODO: Should be set only when opening a file, not when importing
        document.Label = building.Label
        document.CreatedBy = get_property(home, 'Author')
        document.Comment = get_property(home, 'Copyright')
        document.License = get_property(home, 'License')
        document.recompute()

def export(exportList,filename,tessellation=1,colors=None):
    # REF: /home/rostskadat/git/opensource/sweethome3d-code/sweethome3d-code/SweetHome3D/src/com/eteks/sweethome3d/io/HomeFileRecorder.java
    # Creating a zip file with 2 entries (Home, and Home.xml
    if not checkSH3D():
        return
    App.Console.PrintMessage(translate("Arch","file %s successfully created.") % filename)

def import_levels(home):
    """Returns all the levels found in the file.

    Args:
        home (dict): The xml to read the objects from

    Returns:
        list: the list of imported floors
    """
    return list(map(import_level, home['home']['level']))

def import_level(imported_level):
    """Creates and returns a Arch::Floor from the imported_level object

    Args:
        imported_level (dict): the dict object containg the characteristics of the new object

    Returns:
        Arc::Floor: the newly created object
    """
    floor = Arch.makeFloor()
    floor.Label = imported_level['@name']
    floor.Placement.Base.z = dim_sh2fc(float(imported_level['@elevation']))
    floor.Height = dim_sh2fc(float(imported_level['@height']))

    #floor.setExpression("OverallWidth", "Length.Value")

    add_property(floor, "App::PropertyString", "shType", "The element type")
    add_property(floor, "App::PropertyString", "id", "The floor's id")
    add_property(floor, "App::PropertyFloat", "floorThickness", "The floor's slab thickness")
    add_property(floor, "App::PropertyInteger", "elevationIndex", "The floor number")
    add_property(floor, "App::PropertyBool", "viewable", "Whether the floor is viewable")

    floor.shType         = 'level'
    floor.id             = imported_level['@id']
    floor.floorThickness = dim_sh2fc(float(imported_level['@floorThickness']))
    floor.elevationIndex = int(get_attr(imported_level, '@elevationIndex', 0))
    floor.ViewObject.Visibility = get_attr(imported_level, '@visible', 'false') == 'true'

    return floor

def create_default_floor():
    default_floor = Arch.makeFloor()
    default_floor.Label = 'Floor'
    default_floor.Placement.Base.z = 0
    default_floor.Height = 2500

    add_property(default_floor, "App::PropertyString", "shType", "The element type")
    add_property(default_floor, "App::PropertyString", "id", "The floor's id")
    add_property(default_floor, "App::PropertyFloat", "floorThickness", "The floor's slab thickness")

    default_floor.shType         = 'level'
    default_floor.id             = str(uuid.uuid4())
    default_floor.floorThickness = 200

    return default_floor

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

def import_rooms(home, floors):
    """Returns all the rooms found in the file.

    Args:
        home (dict): The xml to read the objects from

    Returns:
        list: the list of imported rooms
    """
    return list(map(partial(import_room, floors), home['home']['room']))

def import_room(floors, imported_room):
    """Creates and returns a Arch::Structure from the imported_room object

    Args:
        imported_room (dict): the dict object containg the characteristics of the new object

    Returns:
        Arc::Structure: the newly created object
    """
    floor = get_floor(floors, get_attr(imported_room, '@level', None))

    pl = App.Placement()
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

    add_property(slab, "App::PropertyString", "shType", "The element type")
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

    slab.shType = 'room'
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

def import_walls(home, floors):
    """Returns the list of imported walls

    Args:
        home (dict): The xml to read the objects from
        floors (list): The list of floor each wall references

    Returns:
        list: the list of imported walls
    """
    if 'wall' in home['home']:
        return list(map(partial(import_wall, floors), home['home']['wall']))
    return []

def import_wall(floors, imported_wall):
    """Creates and returns a Arch::Structure from the imported_wall object

    Args:
        imported_wall (dict): the dict object containg the characteristics of the new object

    Returns:
        Arc::Structure: the newly created object
    """
    floor = get_floor(floors, get_attr(imported_wall, '@level', None))

    if '@heightAtEnd' in imported_wall:
        wall = _make_tappered_wall(floor, imported_wall)
    elif '@arcExtent' in imported_wall:
        # NOT_IMPLEMENTED
        wall = _make_arqued_wall(floor, imported_wall)
    else:
        wall = _make_straight_wall(floor, imported_wall)


    _set_wall_colors(wall, imported_wall)

    baseboards = import_baseboards(wall, imported_wall)
    if len(baseboards):
        App.ActiveDocument.Baseboards.addObjects(baseboards)

    wall.Label = imported_wall['@id']

    add_property(wall, "App::PropertyString", "shType", "The element type")
    add_property(wall, "App::PropertyString", "id", "The wall's id")
    add_property(wall, "App::PropertyString", "wallAtStart", "The Id of the contiguous wall at the start of this wall")
    add_property(wall, "App::PropertyString", "wallAtEnd", "The Id of the contiguous wall at the end of this wall")
    add_property(wall, "App::PropertyString", "pattern", "The pattern of this wall in plan view")
    add_property(wall, "App::PropertyFloat", "leftSideShininess", "The wall's left hand side shininess")
    add_property(wall, "App::PropertyFloat", "rightSideShininess", "The wall's right hand side shininess")

    wall.shType = 'wall'
    wall.wallAtStart = get_attr(imported_wall, '@wallAtStart', '')
    wall.wallAtEnd = get_attr(imported_wall, '@wallAtEnd', '')
    wall.pattern = get_attr(imported_wall, '@pattern', '')
    wall.leftSideShininess = float(get_attr(imported_wall, '@leftSideShininess', 0))
    wall.rightSideShininess = float(get_attr(imported_wall, '@rightSideShininess', 0))

    floor.addObject(wall)
    return wall

def _make_straight_wall(floor, imported_wall):
    """Create a Arch Wall from a line. 

    The constructed mesh has been will be a simple solid with the length width height found in imported_wall

    Args:
        floor (Arch::Structure): The floor the wall belongs to
        imported_wall (dict): the imported wall

    Returns:
        Arch::Wall: the newly created wall
    """
    x_start = float(imported_wall['@xStart'])
    y_start = float(imported_wall['@yStart'])
    z_start = dim_fc2sh(floor.Placement.Base.z)
    x_end = float(imported_wall['@xEnd'])
    y_end = float(imported_wall['@yEnd'])

    pl = App.Placement()
    points = [
        coord_sh2fc(App.Vector(x_start, y_start, z_start)), 
        coord_sh2fc(App.Vector(x_end, y_end, z_start))
    ]
    line = Draft.make_wire(points, placement=pl, closed=False, face=True, support=None)
    wall = Arch.makeWall(line)

    #wall.setExpression('Height', f"<<{floor}>>.height")
    wall.Height = dim_sh2fc(float(get_attr(imported_wall, '@height', dim_fc2sh(floor.Height))))
    wall.Width = dim_sh2fc(float(imported_wall['@thickness']))
    wall.Normal = App.Vector(0, 0, 1)
    return wall

def _make_tappered_wall(floor, imported_wall):
    """Create a Arch Wall from a mesh. 
    
    The constructed mesh has been will have different height at the begining and the end

    Args:
        floor (Arch::Structure): The floor the wall belongs to
        imported_wall (dict): the dict object containg the characteristics of the new object

    Returns:
        Arch::Wall: the newly created wall
    """

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

    height = float(get_attr(imported_wall, '@height', dim_fc2sh(floor.Height)))
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
    transform.scale(scale)
    transform.rotateZ(phi+theta)
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

def _set_wall_colors(wall, imported_wall):
    # The default color of the wall
    topColor = get_attr(imported_wall, '@topColor', 'FF96A9BA')
    if App.GuiUp:
        set_color_and_transparency(wall, topColor)
    topColor = hex2rgb(topColor)
    leftSideColor = topColor
    if '@leftSideColor' in imported_wall:
        leftSideColor = hex2rgb(imported_wall['@leftSideColor'])
    rightSideColor = topColor
    if '@rightSideColor' in imported_wall:
        rightSideColor = hex2rgb(imported_wall['@rightSideColor'])
    
    colors = [leftSideColor,topColor,rightSideColor,topColor,topColor,topColor] 
    if hasattr(wall.ViewObject, "DiffuseColor"):
        wall.ViewObject.DiffuseColor = colors

def import_baseboards(wall, imported_wall):
    """Returns the list of imported baseboard

    Args:
        wall (Arch::Structure): The wall the baseboard belongs to
        imported_wall (dict): The xml to read the objects from

    Returns:
        list: the list of imported baseboards
    """
    if 'baseboard' not in imported_wall:
        return []
    App.ActiveDocument.recompute()
    return list(map(partial(import_baseboard, wall), imported_wall['baseboard']))

def import_baseboard(wall, imported_baseboard):
    """Creates and returns a Part::Extrusion from the imported_baseboard object

    Args:
        imported_baseboard (dict): the dict object containg the characteristics of the new object

    Returns:
        Part::Extrusion: the newly created object
    """
    wall_width = float(wall.Width)
    baseboard_width = dim_sh2fc(imported_baseboard['@thickness'])
    baseboard_height = dim_sh2fc(imported_baseboard['@height'])
    vertexes = wall.Shape.Vertexes

    # The left side is defined as the face on the left hand side when going
    # from (xStart,yStart) to (xEnd,yEnd). I assume the points are always 
    # created in the same order. We then have on the lefthand side the points
    # 1 and 2, while on the righthand side we have the points 4 and 6
    side = imported_baseboard['@attribute']
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

    add_property(baseboard, "App::PropertyString", "shType", "The element type")
    add_property(baseboard, "App::PropertyLink", "parent", "The element parent")

    baseboard.shType = 'baseboard'
    baseboard.parent = wall

    return baseboard

def import_doors(home, floors):
    """Returns the list of imported door

    Args:
        home (dict): The xml to read the objects from

    Returns:
        list: the list of imported doors
    """
    return list(map(partial(import_door, floors), home['home']['doorOrWindow']))

def import_door(floors, imported_door):
    """Creates and returns a Arch::Door from the imported_door object

    Args:
        floors (list): the list of imported levels
        imported_door (dict): the dict object containg the characteristics of the new object

    Returns:
        Arch::Door: the newly created object
    """
    floor = get_floor(floors, get_attr(imported_door, '@level', None))

    window = create_window(floor, imported_door)
    if not window:
        App.Console.PrintError(f"Could not create window from '{imported_door['@id']}'. Skipping\n")
        return None

    add_property(window, "App::PropertyString", "shType", "The element type")
    window.shType = 'doorOrWindow'

    _add_furniture_common_attributes(window, imported_door)
    _add_piece_of_furniture_common_attributes(window, imported_door)

    add_property(window, "App::PropertyFloat", "wallThickness", "")
    add_property(window, "App::PropertyFloat", "wallDistance", "")
    add_property(window, "App::PropertyFloat", "wallWidth", "")
    add_property(window, "App::PropertyFloat", "wallLeft", "")
    add_property(window, "App::PropertyFloat", "wallHeight", "")
    add_property(window, "App::PropertyFloat", "wallTop", "")
    add_property(window, "App::PropertyBool", "wallCutOutOnBothSides", "")
    add_property(window, "App::PropertyBool", "widthDepthDeformable", "")
    add_property(window, "App::PropertyString", "cutOutShape", "")
    add_property(window, "App::PropertyBool", "boundToWall", "")

    window.wallThickness = float(get_attr(imported_door, '@wallThickness', 1))
    window.wallDistance = float(get_attr(imported_door, '@wallDistance', 0))
    window.wallWidth = float(get_attr(imported_door, '@wallWidth', 1))
    window.wallLeft = float(get_attr(imported_door, '@wallLeft', 0))
    window.wallHeight = float(get_attr(imported_door, '@wallHeight', 1))
    window.wallTop = float(get_attr(imported_door, '@wallTop', 0))
    window.wallCutOutOnBothSides = bool(get_attr(imported_door, '@wallCutOutOnBothSides', True))
    window.widthDepthDeformable = bool(get_attr(imported_door, '@widthDepthDeformable', True))
    window.cutOutShape = str(get_attr(imported_door, '@cutOutShape', ''))
    window.boundToWall = bool(get_attr(imported_door, '@boundToWall', True))

    return window

def create_window(floor, imported_door):

    wall = _get_wall(floor, imported_door)

    # NOTE: the window is actually offset by the model's width on X axis
    x = float(imported_door['@x']) - float(imported_door['@width']) / 2
    y = float(imported_door['@y']) + float(imported_door['@depth']) / 2
    elevation = float(get_attr(imported_door, '@elevation', 0))
    z = coord_sh2fc(App.Vector(x, y , dim_fc2sh(floor.Placement.Base.z)+elevation))

    depth = dim_sh2fc(float(imported_door['@depth']))
    width = dim_sh2fc(float(imported_door['@width']))
    height = dim_sh2fc(float(imported_door['@height']))

    # How to choose the face???
    pl = WorkingPlane.getPlacementFromFace(wall.Shape.Faces[0])
    pl.Base = z

    # NOTE: the windows are not imported as meshes, but we use a simple 
    #   correspondance between a catalog ID and a specific window preset from 
    #   the parts library.
    catalog_id = get_attr(imported_door, '@catalogId', None)
    if catalog_id in ("eTeks#fixedWindow85x123", "eTeks#window85x123", "eTeks#doubleWindow126x123"):
        h1 = 70
        h2 = 30
        h3 = 0
        w1 = min(depth, wall.Width)
        w2 = 40
        o1 = 0
        o2 = w1 / 2
        window = Arch.makeWindowPreset('Open 2-pane', width=width, height=height, h1=h1, h2=h2, h3=h3, w1=w1, w2=w2, o1=o1, o2=o2, placement=pl)
    elif catalog_id in ("eTeks#frontDoor", "eTeks#roundedDoor"):
        h1 = 70
        h2 = 30
        h3 = h1+h2
        w1 = min(depth, wall.Width)
        w2 = 40
        o1 = 0
        o2 = w1 / 2
        window = Arch.makeWindowPreset('Simple door', width=width, height=height, h1=h1, h2=h2, h3=h3, w1=w1, w2=w2, o1=o1, o2=o2, placement=pl)
    else:
        print(f"Unknown catalogId {catalog_id} for door {imported_door['@id']}. Skipping")
        return None
    
    window.Normal = pl.Rotation.multVec(App.Vector(0, 0, -1))
    window.Hosts = [wall]
    return window

def _get_window(objects):
    new_objects = App.ActiveDocument.Objects
    for object in new_objects[len(objects):]:
        if Draft.getType(object) == "Window":
            if Draft.getType(object.Base) == "Sketcher::SketchObject":
                return App.ActiveDocument.getObject(object.Name)
    return None

def _get_wall(floor, imported_door):
    x = float(imported_door['@x'])
    y_0 = float(imported_door['@y'])# depends on angle as well
    y_1 = float(imported_door['@y']) + float(imported_door['@depth']) # depends on angle as well
    y_2 = float(imported_door['@y']) - float(imported_door['@depth']) # depends on angle as well
    z = dim_fc2sh(floor.Placement.Base.z) + float(get_attr(imported_door, '@elevation', 0))
    v0 = coord_sh2fc(App.Vector(x, y_0, z))
    v1 = coord_sh2fc(App.Vector(x, y_1, z))
    v2 = coord_sh2fc(App.Vector(x, y_2, z))
    for object in App.ActiveDocument.Objects:
        if Draft.getType(object) == "Wall":
            bb = object.Shape.BoundBox
            if bb.isInside(v0) or bb.isInside(v1) or bb.isInside(v2):
                return object
    print (f"No wall found for door {imported_door['@id']}")
    return None

def import_furnitures(home, zip, floors):
    list(map(partial(import_furniture, zip, floors), home['home']['pieceOfFurniture']))

def import_furniture(zip, floors, imported_furniture):

    # let's read the model first
    model = imported_furniture['@model']
    if model not in zip.namelist():
        raise ValueError(f"Invalid SweetHome3D file: missing model {model}")
    materials = import_materials(imported_furniture)
    mesh = get_mesh_from_model(zip, model, materials)
    furniture = create_furniture(floors, imported_furniture, mesh)
    App.ActiveDocument.Furnitures.addObject(furniture)
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

    add_property(furniture, "App::PropertyString", "shType", "The element type")
    furniture.shType = 'wall'
    _add_furniture_common_attributes(furniture, imported_furniture)
    _add_piece_of_furniture_common_attributes(furniture, imported_furniture)
    _add_piece_of_furniture_horizontal_rotation_attributes(furniture, imported_furniture)
    return furniture

def get_mesh_from_model(zip, model, materials):
    model_path_obj = None
    try:
        # Since mesh.read(model_data) does not work on BytesIO extract it first
        tmp_dir = App.ActiveDocument.TransientDir
        if isdir(join(tmp_dir, model)):
            tmp_dir = join(tmp_dir, str(uuid.uuid4()))
        model_path = zip.extract(member=model, path=tmp_dir)
        model_path_obj = model_path+".obj"
        rename(model_path, model_path_obj)
        mesh = Mesh.Mesh()
        mesh.read(model_path_obj)
    finally:
        if model_path_obj: 
            remove(model_path_obj)
    return mesh

def create_furniture(floors, imported_furniture, mesh):

    floor = get_floor(floors, get_attr(imported_furniture, '@level', None))

    # REF: sweethome3d-code/SweetHome3D/src/com/eteks/sweethome3d/j3d/ModelManager.java:getPieceOfFurnitureNormalizedModelTransformation()
    width = dim_sh2fc(float(imported_furniture['@width']))
    depth = dim_sh2fc(float(imported_furniture['@depth']))
    height = dim_sh2fc(float(imported_furniture['@height']))
    x = float(imported_furniture.get('@x',0))
    y = float(imported_furniture.get('@y',0))
    z = float(imported_furniture.get('@elevation', 0.0))
    angle = float(imported_furniture.get('@angle', 0.0))
    name = imported_furniture['@name']
    mirrored = bool(imported_furniture.get('@modelMirrored', "false") == "true")

    # The meshes are normalized, facing up.
    # Center, Scale, X Rotation && Z Rotation (in FC axes), Move
    bb = mesh.BoundBox
    transform = App.Matrix()
    transform.move(-bb.Center)
    # NOTE: the model is facing up, thus y and z are inverted
    transform.scale(width/bb.XLength, height/bb.YLength, depth/bb.ZLength)
    transform.rotateX(pi/2) # 90º
    transform.rotateZ(-angle)
    level_elevation = dim_fc2sh(floor.Placement.Base.z)
    transform.move(coord_sh2fc(App.Vector(x, y, level_elevation + z + (dim_fc2sh(height) / 2))))
    mesh.transform(transform)

    furniture = App.ActiveDocument.addObject("Mesh::Feature", name)
    furniture.Mesh = mesh
    return furniture

def _add_furniture_common_attributes(furniture, imported_furniture):
    add_property(furniture, "App::PropertyString", "id", "The furniture's id")
    add_property(furniture, "App::PropertyFloat", "angle", "The angle of the furniture")
    add_property(furniture, "App::PropertyBool", "visible", "Whether the object is visible")
    add_property(furniture, "App::PropertyBool", "movable", "Whether the object is movable")
    add_property(furniture, "App::PropertyString", "description", "The object's description")
    add_property(furniture, "App::PropertyString", "information", "The object's information")
    add_property(furniture, "App::PropertyString", "license", "The object's license")
    add_property(furniture, "App::PropertyString", "creator", "The object's creator")
    add_property(furniture, "App::PropertyBool", "modelMirrored", "Whether the object is mirrored")
    add_property(furniture, "App::PropertyBool", "nameVisible", "Whether the object's name is visible")
    add_property(furniture, "App::PropertyFloat", "nameAngle", "The object's name angle")
    add_property(furniture, "App::PropertyFloat", "nameXOffset", "The object's name X offset")
    add_property(furniture, "App::PropertyFloat", "nameYOffset", "The object's name Y offset")
    add_property(furniture, "App::PropertyFloat", "price", "The object's price")

    furniture.id = str(imported_furniture['@id'])
    furniture.angle = float(get_attr(imported_furniture, '@angle', 0))
    furniture.visible = bool(get_attr(imported_furniture, '@visible', True))
    furniture.movable = bool(get_attr(imported_furniture, '@movable', True))
    furniture.description = str(get_attr(imported_furniture, '@description', ''))
    furniture.information = str(get_attr(imported_furniture, '@information', ''))
    furniture.license = str(get_attr(imported_furniture, '@license', ''))
    furniture.creator = str(get_attr(imported_furniture, '@creator', ''))
    furniture.modelMirrored = bool(get_attr(imported_furniture, '@modelMirrored', False))
    furniture.nameVisible = bool(get_attr(imported_furniture, '@nameVisible', False))
    furniture.nameAngle = float(get_attr(imported_furniture, '@nameAngle', 0))
    furniture.nameXOffset = float(get_attr(imported_furniture, '@nameXOffset', 0))
    furniture.nameYOffset = float(get_attr(imported_furniture, '@nameYOffset', 0))
    furniture.price = float(get_attr(imported_furniture, '@price', 0))

def _add_piece_of_furniture_common_attributes(furniture, imported_furniture):
    add_property(furniture, "App::PropertyString", "level", "The furniture's level")
    add_property(furniture, "App::PropertyString", "catalogId", "The furniture's catalog id")
    add_property(furniture, "App::PropertyFloat", "dropOnTopElevation", "")
    add_property(furniture, "App::PropertyString", "model", "The object's mesh file")
    add_property(furniture, "App::PropertyString", "icon", "The object's icon")
    add_property(furniture, "App::PropertyString", "planIcon", "The object's icon for the plan view")
    add_property(furniture, "App::PropertyString", "modelRotation", "The object's model rotation")
    add_property(furniture, "App::PropertyString", "modelCenteredAtOrigin", "The object's center")
    add_property(furniture, "App::PropertyBool", "backFaceShown", "Whether the object's back face is shown")
    add_property(furniture, "App::PropertyString", "modelFlags", "The object's flags")
    add_property(furniture, "App::PropertyFloat", "modelSize", "The object's size")
    add_property(furniture, "App::PropertyBool", "doorOrWindow", "Whether the object is a door or Window")
    add_property(furniture, "App::PropertyBool", "resizable", "Whether the object is resizable")
    add_property(furniture, "App::PropertyBool", "deformable", "Whether the object is deformable")
    add_property(furniture, "App::PropertyBool", "texturable", "Whether the object is texturable")
    add_property(furniture, "App::PropertyString", "staircaseCutOutShape", "")
    add_property(furniture, "App::PropertyFloat", "shininess", "The object's shininess")
    add_property(furniture, "App::PropertyFloat", "valueAddedTaxPercentage", "The object's VAT percentage")
    add_property(furniture, "App::PropertyString", "currency", "The object's price currency")

    furniture.level = str(get_attr(imported_furniture, '@level', ''))
    furniture.catalogId = str(get_attr(imported_furniture, '@catalogId', ''))
    furniture.dropOnTopElevation = float(get_attr(imported_furniture, '@dropOnTopElevation', 0))
    furniture.model = str(get_attr(imported_furniture, '@model', ''))
    furniture.icon = str(get_attr(imported_furniture, '@icon', ''))
    furniture.planIcon = str(get_attr(imported_furniture, '@planIcon', ''))
    furniture.modelRotation = str(get_attr(imported_furniture, '@modelRotation', ''))
    furniture.modelCenteredAtOrigin = str(get_attr(imported_furniture, '@modelCenteredAtOrigin', ''))
    furniture.backFaceShown = bool(get_attr(imported_furniture, '@backFaceShown', False))
    furniture.modelFlags = str(get_attr(imported_furniture, '@modelFlags', ''))
    furniture.modelSize = float(get_attr(imported_furniture, '@modelSize', 0))
    furniture.doorOrWindow = bool(get_attr(imported_furniture, '@doorOrWindow', False))
    furniture.resizable = bool(get_attr(imported_furniture, '@resizable', True))
    furniture.deformable = bool(get_attr(imported_furniture, '@deformable', True))
    furniture.texturable = bool(get_attr(imported_furniture, '@texturable', True))
    furniture.staircaseCutOutShape = str(get_attr(imported_furniture, '@staircaseCutOutShape', ''))
    furniture.shininess = float(get_attr(imported_furniture, '@shininess', 0))
    furniture.valueAddedTaxPercentage = float(get_attr(imported_furniture, '@valueAddedTaxPercentage', 0))
    furniture.currency = str(get_attr(imported_furniture, '@currency', 'EUR'))

def _add_piece_of_furniture_horizontal_rotation_attributes(furniture, imported_furniture):
    add_property(furniture, "App::PropertyBool", "horizontallyRotatable", "Whether the object horizontally rotatable")
    add_property(furniture, "App::PropertyFloat", "pitch", "The object's pitch")
    add_property(furniture, "App::PropertyFloat", "roll", "The object's roll")
    add_property(furniture, "App::PropertyFloat", "widthInPlan", "The object's width in the plan view")
    add_property(furniture, "App::PropertyFloat", "depthInPlan", "The object's depth in the plan view")
    add_property(furniture, "App::PropertyFloat", "heightInPlan", "The object's height in the plan view")

    furniture.horizontallyRotatable = bool(get_attr(imported_furniture, '@horizontallyRotatable', True))
    furniture.pitch = float(get_attr(imported_furniture, '@pitch', 0))
    furniture.roll = float(get_attr(imported_furniture, '@roll', 0))
    furniture.widthInPlan = float(get_attr(imported_furniture, '@widthInPlan', 0))
    furniture.depthInPlan = float(get_attr(imported_furniture, '@depthInPlan', 0))
    furniture.heightInPlan = float(get_attr(imported_furniture, '@heightInPlan', 0))

def import_materials(imported_furniture):
    if 'material' not in imported_furniture:
        return []
    
    imported_materials = imported_furniture['material']
    materials = []
    try:
        for imported_material in imported_materials:
            name = imported_material['@name']
            color = imported_material['@color'] if '@color' in imported_material else 'FF000000'
            shininess = imported_material['@shininess'] if '@shininess' in imported_material else '0.0'
            material = Arch.makeMaterial(
                name=name, 
                color=hex2rgb(color), 
                transparency=hex2transparency(color)
                )
            add_property(material, "App::PropertyFloat", "shininess", "The shininess of the material")
            material.shininess = float(shininess)
            materials.append(material)
    except Exception as e:
        App.Console.PrintError(f"Error while creating material {e}")
    
    return materials

def import_lights(home, zip, floors):
    list(map(partial(import_light, zip, floors), home['home']['light']))

def import_light(zip, floors, imported_light):
    light_appliance = import_furniture(zip, floors, imported_light)

    add_property(light_appliance, "App::PropertyFloat", "power", "The power of the light")
    light_appliance.power = float(get_attr(imported_light, '@power', 0.5))
    light_appliance.shType = 'light'

    import Render
    light_source = imported_light['lightSource']
    x = float(light_source['@x'])
    y = float(light_source['@y'])
    z = float(light_source['@z'])
    diameter = float(light_source['@diameter'])
    color = light_source['@color']
    light, feature, _ = Render.PointLight.create()
    feature.Label = light_appliance.Label
    feature.Placement.Base = coord_sh2fc(App.Vector(x,y,z))
    feature.Radius = dim_sh2fc(diameter / 2)
    feature.Color = hex2rgb(color)
    App.ActiveDocument.Lights.addObject(feature)

    add_property(feature, "App::PropertyString", "shType", "The element type")
    feature.shType = 'lightSource'

    return light

def import_observer_cameras(home):
    return list(map(partial(import_observer_camera), home['home']['observerCamera']))

def import_observer_camera(imported_camera):
    x = float(imported_camera['@x'])
    y = float(imported_camera['@y'])
    z = float(imported_camera['@z'])
    yaw = float(imported_camera['@yaw'])
    pitch = float(imported_camera['@pitch'])
    # ¿How to convert fov to FocalLength?
    fieldOfView = float(imported_camera['@fieldOfView'])

    import Render
    camera, feature, _ = Render.Camera.create()
    feature.Label = imported_camera['@name'] if '@name' in imported_camera else 'ObserverCamera'
    feature.Placement.Base = coord_sh2fc(App.Vector(x,y,z))
    # NOTE: the coordinate system is screen like, thus roll & picth are inverted ZY'X''
    feature.Placement.Rotation.setYawPitchRoll(degrees(yaw), degrees(pitch), 0)
    feature.Projection = "Perspective"
    feature.AspectRatio = 1.33333333 # /home/environment/@photoAspectRatio

    App.ActiveDocument.Cameras.addObject(feature)

    add_property(feature, "App::PropertyString", "shType", "The element type")
    feature.shType = 'observerCamera'

    add_property(feature, "App::PropertyEnumeration", "attribute", "The type of camera")
    feature.attribute = ["observerCamera", "storedCamera", "cameraPath"]
    feature.attribute = imported_camera['@attribute']

    add_property(feature, "App::PropertyBool", "fixedSize", "Whether the object is fixed size")
    feature.fixedSize = bool(get_attr(imported_camera, '@fixedSize', False))

    _add_camera_common_attributes(feature, imported_camera)

    return camera

def _add_camera_common_attributes(feature, imported_camera):
    add_property(feature, "App::PropertyString", "id", "The object horizontally rotatable")
    add_property(feature, "App::PropertyEnumeration", "lens", "The object's lens (PINHOLE | NORMAL | FISHEYE | SPHERICAL)")
    add_property(feature, "App::PropertyFloat", "yaw", "The object's roll")
    add_property(feature, "App::PropertyFloat", "pitch", "The object's width in the plan view")
    add_property(feature, "App::PropertyFloat", "time", "The object's depth in the plan view")
    add_property(feature, "App::PropertyFloat", "fieldOfView", "The object's height in the plan view")
    add_property(feature, "App::PropertyString", "renderer", "The object's height in the plan view")

    feature.id = str(get_attr(imported_camera, '@id', True))
    feature.lens = ["PINHOLE", "NORMAL", "FISHEYE", "SPHERICAL"]
    feature.lens = str(get_attr(imported_camera, '@lens', "PINHOLE"))
    feature.yaw = float(imported_camera['@yaw'])
    feature.pitch = float(imported_camera['@pitch'])
    feature.time = float(get_attr(imported_camera, '@time', 0))
    feature.fieldOfView = float(imported_camera['@fieldOfView'])
    feature.renderer = str(get_attr(imported_camera, '@renderer', ''))

def rgb2hex(r,g,b):
    return "{:02x}{:02x}{:02x}".format(r,g,b)

def hex2rgb(hexcode):
    # We might have transparency as the first 2 digit
    offset = 0 if len(hexcode) == 6 else 2
    return (int(hexcode[offset:offset+2], 16), int(hexcode[offset+2:offset+4], 16), int(hexcode[offset+4:offset+6], 16))

def hex2transparency(hexcode):
    return 50 if DEBUG else 100 - int( int(hexcode[0:2], 16) * 100 / 255 )

def set_color_and_transparency(obj, color):
    if hasattr(obj.ViewObject,"ShapeColor"):
        obj.ViewObject.ShapeColor = hex2rgb(color)
    if hasattr(obj.ViewObject,"Transparency"):
        obj.ViewObject.Transparency = hex2transparency(color)

def get_property(home, property_name):
    for property in home['home']['property']:
        if property['@name'] == property_name:
            return property['@value']
    return None

def coord_fc2sh(vector):
    """Converts FreeCAD to SweetHome coordinate

    Args:
        vector (FreeCAD.Vector): The coordinate in FreeCAD

    Returns:
        FreeCAD.Vector: the SweetHome coordinate
    """
    return App.Vector(vector.x/FACTOR, -vector.y/FACTOR, vector.z/FACTOR)

def coord_sh2fc(vector):
    """Converts SweetHome to FreeCAD coordinate

    Args:
        vector (FreeCAD.Vector): The coordinate in SweetHome

    Returns:
        FreeCAD.Vector: the FreeCAD coordinate
    """
    return App.Vector(vector.x*FACTOR, -vector.y*FACTOR, vector.z*FACTOR)

def dim_fc2sh(dimension):
    """Convert FreeCAD dimension (mm) to SweetHome dimension (cm)

    Args:
        dimension (float): The dimension in FreeCAD

    Returns:
        float: the SweetHome dimension
    """
    return float(dimension)/FACTOR

def dim_sh2fc(dimension):
    """Convert SweetHome dimension (cm) to FreeCAD dimension (mm)

    Args:
        dimension (float): The dimension in SweetHome

    Returns:
        float: the FreeCAD dimension
    """
    return float(dimension)*FACTOR

def get_attr(obj, attribute_name, default_value=None):
    return obj[attribute_name] if attribute_name in obj else default_value

def add_property(obj, property_type, name, description):
    obj.addProperty(property_type, name, "SweetHome3D", description)

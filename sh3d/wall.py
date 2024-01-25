import FreeCAD as App
import Arch, Draft
from .utils import FACTOR, set_color_and_transparency, coord_sh2fc, get_default_placement, dim_sh2fc
from functools import partial

def add_colored_side(wall, face, color, side):
    facebinder = Draft.make_facebinder([(wall, (face))], name=f"{wall.Label} {side}")
    facebinder.Extrusion = 1.0
    set_color_and_transparency(facebinder, color)
    return facebinder

def add_colored_sides(imported_wall, wall):
    """Add a FaceBinder on either side of the wall.

    When the Imported wall has the leftSideColor/rightSideColor attribute set,
    we create a facebinder on each side in order to set the corresponding 
    color.

    Args:
        imported_wall (dict): the wall that is to be imported
        wall (Part): the wall to be constructued

    Returns:
        list: The list of facebinders
    """
    # The left side is defined as the face on the left hand side when going
    # from (xStart,yStart) to (xEnd,yEnd). Namely Face1 (Left) and 
    # Face3 (Right)
    facebinders = []
    if '@leftSideColor' in imported_wall:
        facebinders.append(add_colored_side(wall, "Face1", imported_wall['@leftSideColor'], "leftSide"))
    if '@rightSideColor' in imported_wall:
        facebinders.append(add_colored_side(wall, "Face3", imported_wall['@rightSideColor'], "rightSide"))
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

def import_wall(facebinder_group, baseboard_group, imported_wall):
    x_start = float(imported_wall['@xStart'])
    y_start = float(imported_wall['@yStart'])
    x_end = float(imported_wall['@xEnd'])
    y_end = float(imported_wall['@yEnd'])

    pl = get_default_placement()
    points = [
        coord_sh2fc(App.Vector(x_start, y_start, 0.0)), 
        coord_sh2fc(App.Vector(x_end, y_end, 0.0))
    ]
    line = Draft.make_wire(points, placement=pl, closed=False, face=True, support=None)
    wall = Arch.makeWall(line)
    wall.Height = float(imported_wall['@height'])*FACTOR
    wall.Width = float(imported_wall['@thickness'])*FACTOR
    wall.Label = imported_wall['@id']
    wall.IfcType = "Wall"
    wall.Normal = App.Vector(0, 0, 1)
    if App.GuiUp:
        if '@topColor' in imported_wall:
            set_color_and_transparency(wall, imported_wall['@topColor'])

    App.ActiveDocument.recompute()
    if facebinder_group:
        facebinders = add_colored_sides(imported_wall, wall)
        if len(facebinders):
            facebinder_group.addObjects(facebinders)
    if baseboard_group:
        baseboards = import_baseboards(imported_wall, wall)
        if len(baseboards):
            baseboard_group.addObjects(baseboards)
    wall.addProperty("App::PropertyString", "wallAtStart", "SweetHome3D", "The Id of the contiguous wall at the start of this wall").wallAtStart = imported_wall.get('@wallAtStart', '')
    wall.addProperty("App::PropertyString", "wallAtEnd", "SweetHome3D", "The Id of the contiguous wall at the end of this wall").wallAtEnd = imported_wall.get('@wallAtEnd', '')
    wall.addProperty("App::PropertyString", "pattern", "SweetHome3D", "The pattern of this wall in plan view").pattern = imported_wall.get('@pattern', '')
    return wall

def import_walls(home, facebinder_group, baseboard_group):
    return list(map(partial(import_wall, facebinder_group, baseboard_group), home['home']['wall']))


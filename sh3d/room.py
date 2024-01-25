import FreeCAD, Arch, Draft
from .utils import set_color_and_transparency, get_default_placement, coord_sh2fc

def import_room(imported_room):
    pl = get_default_placement()
    points = []
    for point in imported_room['point']:
        points.append(coord_sh2fc(FreeCAD.Vector(float(point['@x']), float(point['@y']), 0.0)))
    line = Draft.make_wire(points, placement=pl, closed=True, face=True, support=None)
    slab = Arch.makeStructure(line, height=200)
    slab.Label = imported_room['@name']
    slab.IfcType = "Slab"
    slab.Normal = FreeCAD.Vector(0,0,-1)
    if FreeCAD.GuiUp:
        set_color_and_transparency(slab, imported_room['@floorColor'])
        if '@ceilingColor' in imported_room:
            ceiling_color = imported_room['@ceilingColor']
    slab.addProperty("App::PropertyFloat", "nameXOffset", "SweetHome3D", "The room's name x offset").nameXOffset = float(imported_room.get('@nameXOffset', 0))
    slab.addProperty("App::PropertyFloat", "nameYOffset", "SweetHome3D", "The room's name y offset").nameYOffset = float(imported_room.get('@nameYOffset', 0))
    slab.addProperty("App::PropertyBool", "areaVisible", "SweetHome3D", "Whether the area of the room is displayed in the plan view").areaVisible = bool(imported_room.get('@areaVisible', False))
    slab.addProperty("App::PropertyFloat", "areaXOffset", "SweetHome3D", "The room's area annotation x offset").areaXOffset = float(imported_room.get('@areaXOffset', 0))
    slab.addProperty("App::PropertyFloat", "areaYOffset", "SweetHome3D", "The room's area annotation y offset").areaYOffset = float(imported_room.get('@areaYOffset', 0))
    return slab

def import_rooms(home):
    return list(map(import_room, home['home']['room']))


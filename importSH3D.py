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
from sh3d import import_rooms, import_walls, import_furnitures, import_furniture
from sh3d.utils import get_property, coord_sh2fc, dim_sh2fc, hex2rgb, add_property
import Arch
from functools import partial
from math import degrees

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



def import_light(zip, furniture_group, light_group, imported_light):
    light_appliance = import_furniture(zip, furniture_group, imported_light)
    add_property(light_appliance, "App::PropertyFloat", "power", "The power of the light")
    light_appliance.power = float(imported_light['@power'])
    import Render
    light_source = imported_light['lightSource']
    x = float(light_source['@x'])
    y = float(light_source['@y'])
    z = float(light_source['@z'])
    diameter = float(light_source['@diameter'])
    color = light_source['@color']
    light, feature, _ = Render.PointLight.create()
    light.fpo.Label = light_appliance.Label
    light.fpo.Placement.Base = coord_sh2fc(App.Vector(x,y,z))
    light.fpo.Radius = dim_sh2fc(diameter / 2)
    light.fpo.Color = hex2rgb(color)
    if light_group:
        light_group.addObject(feature)
    return light


def import_lights(home, zip, furniture_group, light_group):
    return list(map(partial(import_light, zip, furniture_group, light_group), home['home']['light']))


def import_observer_camera(camera_group, imported_camera):
    x = float(imported_camera['@x'])
    y = float(imported_camera['@y'])
    z = float(imported_camera['@z'])
    yaw = float(imported_camera['@yaw'])
    pitch = float(imported_camera['@pitch'])
    # ¿How to convert fov to FocalLength?
    fieldOfView = float(imported_camera['@fieldOfView'])

    import Render
    camera, feature, _ = Render.Camera.create()
    camera.fpo.Label = imported_camera['@name'] if '@name' in imported_camera else 'ObserverCamera'
    camera.fpo.Placement.Base = coord_sh2fc(App.Vector(x,y,z))
    # NOTE: the coordinate system is screen like, thus roll & picth are inverted ZY'X''
    camera.fpo.Placement.Rotation.setYawPitchRoll(degrees(yaw), degrees(pitch), 0)
    camera.fpo.Projection = "Perspective"
    camera.fpo.AspectRatio = 1.33333333 # /home/environment/@photoAspectRatio

    add_property(camera.fpo, "App::PropertyEnumeration", "attribute", "The type of camera")
    camera.fpo.attribute = ["observerCamera", "storedCamera", "cameraPath"]
    camera.fpo.attribute = imported_camera['@attribute']
    add_property(camera.fpo, "App::PropertyEnumeration", "lens", "The lens of the camera")
    camera.fpo.lens = ["PINHOLE", "NORMAL", "FISHEYE", "SPHERICAL"]
    camera.fpo.lens = imported_camera['@lens']
    if camera_group:
        camera_group.addObject(feature)
    return camera


def import_observer_cameras(home, camera_group):
    return list(map(partial(import_observer_camera, camera_group), home['home']['observerCamera']))


def read(filename):
    "reads a SH3D file"
    # REF: SweetHome3D/src/com/eteks/sweethome3d/io/HomeXMLHandler.java

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
        home = xmltodict.parse(zip.read("Home.xml"), force_list=('baseboard', 'light', 'material', 'pieceOfFurniture', 'room', 'wall'))
        rooms = import_rooms(home)

        facebinder_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Facebinders")
        baseboard_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Baseboards")
        light_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Lights")
        camera_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Cameras")

        walls = import_walls(home, facebinder_group, baseboard_group)
        furniture_group = App.ActiveDocument.addObject("App::DocumentObjectGroup","Furnitures")
        furnitures = import_furnitures(home, zip, furniture_group)
        lights = import_lights(home, zip, furniture_group, light_group)
        cameras = import_observer_cameras(home, camera_group)

        floor = Arch.makeFloor(rooms + walls)
        building = Arch.makeBuilding([ floor ])
        building.Label = home['home']['label']['text']
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

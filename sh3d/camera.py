import FreeCAD as App
from functools import partial
from .utils import coord_sh2fc, add_property

from math import degrees


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



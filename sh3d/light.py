import FreeCAD as App
from functools import partial
from .utils import  dim_sh2fc, coord_sh2fc, hex2rgb, add_property
from .furniture import import_furniture


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

import FreeCAD as App
import Mesh, Part, Arch
from .utils import  dim_sh2fc, coord_sh2fc, dim_fc2sh, hex2rgb, hex2transparency, add_property
from functools import partial
from os import rename, remove
from math import pi
from PySide.QtCore import QT_TRANSLATE_NOOP, Qt

if App.GuiUp:
    from draftutils.translate import translate
else:
    # \cond
    def translate(context,text):
        return text
    # \endcond

def get_mesh_from_model(zip, model, materials):
    model_path_obj = None
    try:
        # Since mesh.read(model_data) does not work on BytesIO extract it first
        model_path = zip.extract(member=model, path=App.ActiveDocument.TransientDir)
        model_path_obj = model_path+".obj"
        rename(model_path, model_path_obj)
        mesh = Mesh.Mesh()
        mesh.read(model_path_obj)
        mesh.fillupHoles(1000)
    finally:
        if model_path_obj: 
            remove(model_path_obj)
    return mesh


def create_furniture_mesh(imported_furniture, mesh):
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
    level_elevation = 0 # TODO: should be read from the level
    transform.move(coord_sh2fc(App.Vector(x, y, level_elevation + z + (dim_fc2sh(height) / 2))))
    mesh.transform(transform)

    furniture = App.ActiveDocument.addObject("Mesh::Feature", name)
    furniture.Mesh = mesh
    furniture.addProperty("App::PropertyString", "catalogId", "SweetHome3D", "The Furniture's CatalogID").catalogId = imported_furniture.get('@catalogId', '')
    furniture.addProperty("App::PropertyString", "creator", "SweetHome3D", "The Furniture's creator").creator = imported_furniture.get('@creator', '')
    return furniture

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

def import_furniture(zip, furniture_group, imported_furniture):
    # let's read the model first
    model = imported_furniture['@model']
    if model not in zip.namelist():
        raise ValueError(f"Invalid SweetHome3D file: missing model {model}")
    try:
        materials = import_materials(imported_furniture)

        mesh = get_mesh_from_model(zip, model, materials)
        furniture = create_furniture_mesh(imported_furniture, mesh)
        if furniture_group:
            furniture_group.addObject(furniture)

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
        return furniture
    except Part.OCCError as e:
        App.Console.PrintError(f"Invalid mesh for '{imported_furniture['@name']}'. Skipping\n")
        return None

def import_furnitures(home, zip, furniture_group):
    return list(map(partial(import_furniture, zip, furniture_group), home['home']['pieceOfFurniture']))



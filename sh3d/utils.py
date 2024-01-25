import FreeCAD

# SweetHome3D is in cm while FreeCAD is in mm
FACTOR = 10

def rgb2hex(r,g,b):
    return "{:02x}{:02x}{:02x}".format(r,g,b)

def hex2rgb(hexcode):
    # We might have transparency as the first 2 digit
    offset = 0 if len(hexcode) == 6 else 2
    return (int(hexcode[offset:offset+2], 16), int(hexcode[offset+2:offset+4], 16), int(hexcode[offset+4:offset+6], 16))

def hex2transparency(hexcode):
    return 100 - int( int(hexcode[0:2], 16) * 100 / 255 )

def set_color_and_transparency(obj, color):
    if hasattr(obj.ViewObject,"ShapeColor"):
        obj.ViewObject.ShapeColor = hex2rgb(color)
    if hasattr(obj.ViewObject,"Transparency"):
        obj.ViewObject.Transparency = hex2transparency(color)

def get_default_placement():
    pl = FreeCAD.Placement()
    pl.Base = FreeCAD.Vector(0.0, 0.0, 0.0)
    return pl

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
    return FreeCAD.Vector(vector.x/FACTOR, -vector.y/FACTOR, vector.z/FACTOR)

def coord_sh2fc(vector):
    """Converts SweetHome to FreeCAD coordinate 

    Args:
        vector (FreeCAD.Vector): The coordinate in SweetHome

    Returns:
        FreeCAD.Vector: the FreeCAD coordinate
    """
    return FreeCAD.Vector(vector.x*FACTOR, -vector.y*FACTOR, vector.z*FACTOR)

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


def add_property(obj, property_type, name, description):
    obj.addProperty(property_type, name, "SweetHome3D", description)

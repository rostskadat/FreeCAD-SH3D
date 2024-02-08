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


#\cond
import os
import FreeCAD
import FreeCADGui
import sh3d

if FreeCAD.GuiUp:
    import FreeCADGui
    from draftutils.translate import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt,txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond

def checkSH3D():
    return True

def open(filename):
    """called when freecad wants to open a file

    Args:
        filename (str): the filename to be opened

    Returns:
        FreeCAD.Document: the newly imported document
    """
    if not checkSH3D():
        return
    docname = os.path.splitext(os.path.basename(filename))[0]
    doc = FreeCAD.newDocument(docname)
    doc.Label = docname
    FreeCAD.ActiveDocument = doc
    read(filename)
    return doc

def insert(filename,docname):
    """called when freecad wants to import a file

    Args:
        filename (str): the filename to be inserted
        docname (FreeCAD.Document): the document to insert into

    Returns:
        FreeCAD.Document: the amended document
    """
    if not checkSH3D():
        return
    try:
        doc = FreeCAD.getDocument(docname)
    except NameError:
        doc = FreeCAD.newDocument(docname)
    FreeCAD.ActiveDocument = doc
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
    if not FreeCAD.ActiveDocument:
        FreeCAD.Console.PrintError("No active document. Aborting\n")
        return
    
    sh3d.import_sh3d(filename)

    FreeCADGui.SendMsgToActiveView("ViewFit")

def export(exportList, filename, tessellation=1, colors=None):
    # REF: sweethome3d-code/SweetHome3D/src/com/eteks/sweethome3d/io/HomeFileRecorder.java
    # Creating a zip file with 2 entries (Home, and Home.xml)
    if not checkSH3D():
        return
    FreeCAD.Console.PrintMessage(translate("Arch","file %s successfully created.") % filename)

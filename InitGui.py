#***************************************************************************
#*                                                                        *
#*   Copyright (c) 2016                                                     *  
#*   <rostskadat@gmail.com>                                         * 
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify*
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of    *
#*   the License, or (at your option) any later version.                *
#*   for detail see the LICENCE text file.                                *
#*                                                                        *
#*   This program is distributed in the hope that it will be useful,    *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the        *
#*   GNU Library General Public License for more details.                *
#*                                                                        *
#*   You should have received a copy of the GNU Library General Public    *
#*   License along with this program; if not, write to the Free Software*
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307*
#*   USA                                                                *
#*                                                                        *
#************************************************************************

__title__="FreeCAD SweetHome3D Importer"
__author__ = "Julien Masnada"
__url__ = "https://github.com/rostskadat"
__vers__ ="py3.01"

import os
import FreeCAD
import FreeCADGui

import sys
if sys.version_info[0] !=2:
    from importlib import reload
reload(sys)

class SweetHome3DWorkbench(FreeCADGui.Workbench):
    """The SweetHome3D workbench definition."""

    def __init__(self):
        def QT_TRANSLATE_NOOP(context, text):
            return text

        __dirname__ = os.path.join(FreeCAD.getResourceDir(), "Mod", "FreeCAD-SH3D")
        if not os.path.isdir(__dirname__):
            __dirname__ = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "FreeCAD-SH3D")
        if not os.path.isdir(__dirname__):
            FreeCAD.Console.PrintError("Failed to determine the install location of the SweetHome3D workbench. Check your installation.\n")
        _tooltip = ("The SweetHome3D workbench is used to import SweetHome3D materials")
        self.__class__.ResourceDir = os.path.join(__dirname__, "Resources")
        self.__class__.Icon = os.path.join(self.ResourceDir, "icons", "SweetHome3DWorkbench.svg")
        self.__class__.MenuText = QT_TRANSLATE_NOOP("SweetHome3D", "SweetHome3D")
        self.__class__.ToolTip = QT_TRANSLATE_NOOP("SweetHome3D", _tooltip)
        self.__class__.Version = "0.0.1"

    def Initialize(self):
        """When the workbench is first loaded."""

        def QT_TRANSLATE_NOOP(context, text):
            return text

        import sh3d

        self.toolbar = [ "SweetHome3D_Import", ]

        # Set up toolbars
        from draftutils.init_tools import init_toolbar, init_menu
        init_toolbar(self, QT_TRANSLATE_NOOP("Workbench", "SweetHome3D tools"), self.toolbar)
        init_menu(self, QT_TRANSLATE_NOOP("Workbench", "SweetHome3D"), self.toolbar)

        FreeCADGui.addIconPath(":/icons")
        FreeCADGui.addLanguagePath(":/translations")
        FreeCAD.Console.PrintLog('Loading SweetHome3D workbench, done.\n')

    def Activated(self):
        """When entering the workbench."""
        import importlib
        modules = [module for name,module in sys.modules.items() if 'sh3d' in name]
        list(map(lambda module: importlib.reload(module), modules))
        FreeCAD.Console.PrintLog("SweetHome3D workbench activated.\n")

    def Deactivated(self):
        """When leaving the workbench."""
        FreeCAD.Console.PrintLog("SweetHome3D workbench deactivated.\n")

    def GetClassName(self):
        """Type of workbench."""
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(SweetHome3DWorkbench)

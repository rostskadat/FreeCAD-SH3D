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

import os
import FreeCAD
import FreeCADGui
import sh3d
from PySide2 import QtGui, QtWidgets
from PySide.QtCore import QT_TRANSLATE_NOOP


class SH3D_Import:
    """SweetHome3D Import command definition
    """
    def GetResources(self):
        __dirname__ = os.path.join(FreeCAD.getResourceDir(), "Mod", "FreeCAD-SH3D")
        if not os.path.isdir(__dirname__):
            __dirname__ = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "FreeCAD-SH3D")
        if not os.path.isdir(__dirname__):
            FreeCAD.Console.PrintError("Failed to determine the install location of the SweetHome3D workbench. Check your installation.\n")

        return {'Pixmap'  : os.path.join(__dirname__, "Resources", "icons", "SH3D_Import.svg"),
                'MenuText': QT_TRANSLATE_NOOP("SH3D","Import SweetHome3D files."),
                'Accel': "I, S",
                'ToolTip': QT_TRANSLATE_NOOP("SH3D","Import SweetHome3D files.")}

    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        """Shows the GeoData Import UI"""
        self.SH3DFilename = None

        self.dialog = FreeCADGui.PySideUic.loadUi(
            os.path.join(os.path.dirname(__file__), "SH3D_Import.ui")
        )
        self.dialog.sh3dSelectFile.clicked.connect(self.onSH3DSelectFile)
        self.dialog.sh3dFilename.textChanged.connect(self.onSH3DFilenameChanged)
        self.dialog.btnImport.clicked.connect(self.onImport)
        self.dialog.btnClose.clicked.connect(self.onClose)
        self.dialog.progressBar.setVisible(False)
        self.dialog.status.setVisible(False)

        # restore window geometry from stored state
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/SH3D")
        self.dialog.resize(pref.GetInt("WindowWidth", 800), pref.GetInt("WindowHeight", 600))
        self.dialog.setWindowIcon(QtGui.QIcon(":Resources/icons/SH3D_Import.svg"))

        self.updateSH3DFields()

        # center the dialog over the FreeCAD window
        mw = FreeCADGui.getMainWindow()
        self.dialog.move(
            mw.frameGeometry().topLeft()
            + mw.rect().center()
            - self.dialog.rect().center()
        )
        # Non-modal
        self.dialog.show()

    def onSH3DSelectFile(self):
        """Callback to open the file picker
        """
        self._onSelectFile("SweetHome 3D Files (*.sh3d)", "LastSH3DSelectDirname", "SH3DFilename", SH3D_Import.updateSH3DFields)

    def onSH3DFilenameChanged(self, filename):
        """Callback when the user changes the filename
        """
        self._onFilenameChanged(filename, "LastSH3DSelectDirname", "SH3DFilename", SH3D_Import.updateSH3DFields)

    def _onSelectFile(self, file_type, pref_name, attr_name, upd_function):
        """Call the file picker for the specified file.

        Args:
            file_type (str): The file type description used in the file picker UI
            pref_name (str): The preference name to set to remember the last user path
            attr_name (str): The attribute name to set on succeful file selection
            upd_function (func): The argument less function to call when the file has been updated
        """

        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/SH3D")
        home_dir = os.path.expanduser('~')
        file_dirname = pref.GetString(pref_name, home_dir)
        if not os.path.isdir(file_dirname):
            file_dirname = home_dir
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.dialog,
            QT_TRANSLATE_NOOP("SH3D", "Import File"),
            file_dirname,
            QT_TRANSLATE_NOOP("SH3D", file_type)
        )
        pref.SetString(pref_name, os.path.dirname(filename))
        if os.path.isfile(filename):
            setattr(self, attr_name, filename)
            upd_function(self)

    def _onFilenameChanged(self, filename, pref_name, attr_name, upd_function):
        if os.path.isfile(filename):
            pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/SH3D")
            pref.SetString(pref_name, os.path.dirname(filename))
            setattr(self, attr_name, filename)
            upd_function(self)

    def updateSH3DFields(self):
        """Update the dialog filename.
        """
        self.dialog.sh3dFilename.setText(self.SH3DFilename)

    def onImport(self):
        self.dialog.progressBar.setVisible(True)
        self.dialog.status.setVisible(True)

        FreeCAD.ActiveDocument.openTransaction("SH3D_Import")
        FreeCADGui.doCommand("# import sh3d")
        fn = self.SH3DFilename
        join_wall = self.dialog.joinWall.isChecked()
        import_doors = self.dialog.importDoors.isChecked()
        import_furnitures = self.dialog.importFurnitures.isChecked()
        import_lights = self.dialog.importLights.isChecked()
        import_cameras = self.dialog.importCameras.isChecked()
        cmd =  f"# sh3d.import_sh3d('{fn}', {join_wall}, {import_doors}, {import_furnitures}, {import_lights}, {import_cameras})"
        FreeCADGui.doCommand(cmd)
        from importlib import reload
        import sh3d.import_sh3d
        reload(sh3d.import_sh3d)
        sh3d.import_sh3d.import_sh3d(
                self.SH3DFilename, 
                self.dialog.joinWall.isChecked(),
                self.dialog.importDoors.isChecked(),
                self.dialog.importFurnitures.isChecked(),
                self.dialog.importLights.isChecked(),
                self.dialog.importCameras.isChecked(),
                self.onImportProgress)

        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
        self.dialog.progressBar.setVisible(False)

    def onClose(self):
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/SH3D")
        pref.SetInt("WindowWidth", self.dialog.frameSize().width())
        pref.SetInt("WindowHeight", self.dialog.frameSize().height())
        self.dialog.done(0)

    def onImportProgress(self, progress, status):
        if FreeCAD.GuiUp:
            self.dialog.progressBar.setValue(progress)
            if status:
                self.dialog.status.setText(status)
            FreeCADGui.updateGui()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('SH3D_Import', SH3D_Import())

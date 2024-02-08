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
from PySide2 import QtGui, QtWidgets

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

class _CommandImport:
    """SweetHome3D Import command definition
    """
    def GetResources(self):
        return {'Pixmap'  : 'SH3D_Import',
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

        self.dialog.btnImport.setIcon(
            QtGui.QIcon.fromTheme("edit-undo", QtGui.QIcon(":/Resources/icons/SH3D_Import.svg"))
        )
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
        self._onSelectFile("SweetHome 3D Files (*.sh3d)", "LastSH3DSelectDirname", "SH3DFilename", _CommandImport.updateSH3DFields)

    def onCsvFilenameChanged(self, filename):
        """Callback when the user changes the filename
        """
        self._onFilenameChanged(filename, "LastSH3DSelectDirname", "SH3DFilename", _CommandImport.updateSH3DFields)

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
        try:
            sh3d.import_sh3d(self.SH3DFilename, self.dialog.progressBar, self.dialog.status)
        except:
            FreeCAD.Console.PrintError("No active document. Aborting\n")
        self.dialog.progressBar.setVisible(False)

    def onClose(self):
        self.dialog.done(0)

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('SH3D_Import', _CommandImport())

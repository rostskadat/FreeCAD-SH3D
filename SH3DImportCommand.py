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
import json
import os
import FreeCAD
import FreeCADGui
import sh3d
from PySide2 import QtGui, QtCore, QtWidgets
import xml.etree.ElementTree as ET

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
    pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/SweetHome3D")
    default_ = pref.GetInt("ColladaMesher",0)

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

class _CommandImport:
    """SweetHome3D Import command definition

    Returns:
        _type_: _description_
    """
    def GetResources(self):
        return {'Pixmap'  : 'SweetHome3D_Import',
                'MenuText': QT_TRANSLATE_NOOP("SweetHome3D","Import SweetHome3D files."),
                'Accel': "I, S",
                'ToolTip': QT_TRANSLATE_NOOP("SweetHome3D","Import SweetHome3D files.")}

    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        """Shows the GeoData Import UI"""
        self.Browser = None
        self.Altitude = 0.0
        self.CsvFilename = None
        self.GpxFilename = None
        self.EmirFilename = None
        self.LidarFilename = None

        self.dialog = FreeCADGui.PySideUic.loadUi(
            os.path.join(os.path.dirname(__file__), "GeoDataImportDialog.ui")
        )

        self.dialog.tabs.currentChanged.connect(self.onTabBarClicked)
        self.dialog.osmLocationPresets.currentIndexChanged.connect(self.onOsmLocationPresetSelected)
        self.dialog.osmOpenBrowserWindow.clicked.connect(self.onOsmOpenBrowserWindow)
        self.dialog.osmGetCoordFromBrowser.clicked.connect(self.onOsmGetCoordFromBrowser)
        self.dialog.osmUrl.textChanged.connect(self.onOsmUrlChanged)
        self.dialog.osmZoom.valueChanged.connect(self.onOsmZoomChanged)
        self.dialog.osmLatitude.valueChanged.connect(self.onOsmLatitudeChanged)
        self.dialog.osmLongitude.valueChanged.connect(self.onOsmLongitudeChanged)

        self.dialog.csvLatitude.valueChanged.connect(self.onCsvLatitudeChanged)
        self.dialog.csvLongitude.valueChanged.connect(self.onCsvLongitudeChanged)
        self.dialog.csvSelectFile.clicked.connect(self.onCsvSelectFile)
        self.dialog.csvFilename.textChanged.connect(self.onCsvFilenameChanged)

        self.dialog.gpxLatitude.valueChanged.connect(self.onGpxLatitudeChanged)
        self.dialog.gpxLongitude.valueChanged.connect(self.onGpxLongitudeChanged)
        self.dialog.gpxAltitude.valueChanged.connect(self.onGpxAltitudeChanged)
        self.dialog.gpxSelectFile.clicked.connect(self.onGpxSelectFile)
        self.dialog.gpxFilename.textChanged.connect(self.onGpxFilenameChanged)

        self.dialog.emirSelectFile.clicked.connect(self.onEmirSelectFile)
        self.dialog.emirFilename.textChanged.connect(self.onEmirFilenameChanged)

        self.dialog.lidarSelectFile.clicked.connect(self.onLidarSelectFile)
        self.dialog.lidarFilename.textChanged.connect(self.onLidarFilenameChanged)

        self.dialog.btnImport.clicked.connect(self.onImport)
        self.dialog.btnClose.clicked.connect(self.onClose)
        self.dialog.progressBar.setVisible(False)
        self.dialog.status.setVisible(False)

        # restore window geometry from stored state
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/GeoData")
        self.dialog.resize(pref.GetInt("WindowWidth", 800), pref.GetInt("WindowHeight", 600))
        self.dialog.tabs.setCurrentIndex(pref.GetInt("ImportDialogLastOpenTab", 0))
        self.dialog.setWindowIcon(QtGui.QIcon(":Resources/icons/GeoData_Import.svg"))

        global GCP_ELEVATION_API_KEY
        GCP_ELEVATION_API_KEY = pref.GetString("GCP_ELEVATION_API_KEY")

        self.dialog.osmLocationPresets.addItem(QT_TRANSLATE_NOOP("GeoData", "Select a location ..."))
        self.LocationPresets = []
        resource_dir = FreeCADGui.activeWorkbench().ResourceDir
        with open(os.path.join(resource_dir, 'Presets', 'osm.json')) as f:
            presets = json.load(f)
            for preset in presets["osm"]:
                self.LocationPresets.append(preset)
                self.dialog.osmLocationPresets.addItem(preset['name'])
        self.dialog.osmLocationPresets.setCurrentIndex(pref.GetInt("LocationPresetIndex", 0))

        self.updateCsvFields()
        self.updateCsvCoordinates()
        self.updateGpxFields()
        self.updateGpxCoordinates()
        self.updateEmirFields()

        self.dialog.btnImport.setIcon(
            QtGui.QIcon.fromTheme("edit-undo", QtGui.QIcon(":/Resources/icons/GeoData_Import.svg"))
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

    def onCsvSelectFile(self):
        """Callback to open the file picker
        """
        self._onSelectFile("CSV Files (*.csv *.tsv)", "LastCsvSelectDirname", "CsvFilename", _CommandImport.updateCsvFields)
        if os.path.isfile(self.CsvFilename):
            with open(self.CsvFilename, "r") as f:
                self.CsvContent = f.read()
            self.updateCsvFields()

    def onCsvFilenameChanged(self, filename):
        self._onFilenameChanged(filename, "LastCsvSelectDirname", "CsvFilename", _CommandImport.updateCsvFields)
        if os.path.isfile(self.CsvFilename):
            with open(self.CsvFilename, "r") as f:
                self.CsvContent = f.read()
            self.updateCsvFields()

    def onImport(self):
        self.dialog.progressBar.setVisible(True)
        self.dialog.status.setVisible(True)
        import_osm(
                self.Latitude,
                self.Longitude,
                self.Zoom,
                GCP_ELEVATION_API_KEY and self.dialog.osmDownloadAltitude.isChecked(),
                self.dialog.progressBar,
                self.dialog.status)
        self.dialog.progressBar.setVisible(False)

    def onClose(self):
        self.dialog.done(0)

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('SweetHome3D_Import', _CommandImport())

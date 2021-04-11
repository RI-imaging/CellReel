import gc
import pkg_resources
import signal
import sys
import traceback

import qpimage
from PyQt5 import uic, QtCore, QtWidgets
import pyqtgraph as pg

from .wiz_init import InitWizard
from .dlg_open import OpenDialog
from ._version import version as __version__


# global plotting configuration parameters
pg.setConfigOption("background", None)
pg.setConfigOption("antialias", False)
pg.setConfigOption("imageAxisOrder", "row-major")


# Disable HDF5 compression
qpimage.image_data.COMPRESSION = {}


class CellReelMain(QtWidgets.QMainWindow):
    instances = []

    def __init__(self, *args, **kwargs):
        """CellReel main application"""
        super(CellReelMain, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename("cellreel", "main.ui")
        uic.loadUi(path_ui, self)
        CellReelMain.instances.append(self)
        self.setWindowTitle("CellReel {}".format(__version__))
        self.tabWidget.currentChanged.connect(self.on_tab_changed)
        self.actionNew_Session.triggered.connect(self.on_session_new)
        self.actionOpen_Session.triggered.connect(self.on_session_open)
        self.tabWidget.setEnabled(False)
        self.has_data = False
        # if "--version" was specified, print the version and exit
        if "--version" in sys.argv:
            print(__version__)
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents,
                                                 300)
            sys.exit(0)

    def closeEvent(self, event):
        # remove reference to allow garbage collection
        CellReelMain.instances.remove(self)
        # reduce memory leak by removing circular references
        del self.widget_sino.data
        del self.widget_sino
        del self.widget_reco
        del self.widget_info
        self.deleteLater()
        # force garbage collection
        gc.collect()

    def session_load(self, path):
        """Load a session from a path"""
        if not self.has_data:
            self.has_data = True
            self.setWindowTitle("CellReel {} [{}]".format(__version__,
                                                          path.name))
            self.widget_sino.load(path)
            self.widget_reco.load(path)
            self.widget_info.load(path)
            self.tabWidget.setEnabled(True)
        else:
            new = CellReelMain()
            new.session_load(path)
            new.show()

    def on_session_open(self):
        """Let the user choose a session path and load it"""
        self.open_dialog = OpenDialog()
        if self.open_dialog.exec_():
            path = self.open_dialog.get_path()
            if path:
                self.session_load(path)

    def on_session_new(self):
        """Let the user create a new session using the InitWizard"""
        self.init_wizard = InitWizard()
        if self.init_wizard.exec_():
            path = self.init_wizard.path
            self.session_load(path)

    def on_tab_changed(self):
        """Trigger events that need to be run when the current tab changed"""
        self.widget_sino.pushButton_play.setChecked(False)
        if self.tabWidget.currentIndex() == 1:
            self.widget_reco.update_sino_data()


def excepthook(etype, value, trace):
    """
    Handler for all unhandled exceptions.

    Parameters
    ----------
    etype: Exception
        exception type (`SyntaxError`, `ZeroDivisionError`, etc...)
    value: str
        exception error message
    trace:
        traceback header, if any (otherwise, it prints the
        standard Python header: ``Traceback (most recent call last)``
    """
    vinfo = "Unhandled exception in CellReel version {}:\n".format(__version__)
    tmp = traceback.format_exception(etype, value, trace)
    exception = "".join([vinfo]+tmp)

    errorbox = QtWidgets.QMessageBox()
    errorbox.addButton(QtWidgets.QPushButton('Close'),
                       QtWidgets.QMessageBox.YesRole)
    errorbox.addButton(QtWidgets.QPushButton(
        'Copy text && Close'), QtWidgets.QMessageBox.NoRole)
    errorbox.setText(exception)
    ret = errorbox.exec_()
    if ret == 1:
        cb = QtWidgets.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        cb.setText(exception)


# Make Ctr+C close the app
signal.signal(signal.SIGINT, signal.SIG_DFL)
# Display exception hook in separate dialog instead of crashing
sys.excepthook = excepthook

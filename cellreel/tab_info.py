import collections
import numbers
import pathlib
import pkg_resources

import numpy as np
from PyQt5 import uic, QtWidgets

from cellreel.sino import sino_view


class InfoWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super(InfoWidget, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename("cellreel", "tab_info.ui")
        uic.loadUi(path_ui, self)
        self.path = None

    def load(self, path):
        """Make available all session data"""
        path = pathlib.Path(path)
        sv = sino_view.SinoView(path / "sinogram.h5")

        # General data
        for key in INFO_GENERAL:
            value = INFO_GENERAL[key](sv)
            if isinstance(value, numbers.Number):
                value = "{:.5g}".format(value)
            lname = QtWidgets.QLabel(key, parent=self)
            lvalue = QtWidgets.QLabel(str(value), parent=self)
            self.formLayout_general.addRow(lname, lvalue)

        # QP data
        for key in INFO_QP:
            value = INFO_QP[key](sv)
            if isinstance(value, numbers.Number):
                value = "{:.5g}".format(value)
            lname = QtWidgets.QLabel(key, parent=self)
            lvalue = QtWidgets.QLabel(str(value), parent=self)
            self.formLayout_qp.addRow(lname, lvalue)

        # FL data
        if sv.has_fli():
            for key in INFO_FL:
                value = INFO_FL[key](sv)
                if isinstance(value, numbers.Number):
                    value = "{:.5g}".format(value)
                lname = QtWidgets.QLabel(key, parent=self)
                lvalue = QtWidgets.QLabel(str(value), parent=self)
                self.formLayout_fl.addRow(lname, lvalue)
            self.groupBox_fl.show()
        else:
            self.groupBox_fl.hide()


INFO_GENERAL = collections.OrderedDict()
INFO_GENERAL["Session path"] = lambda sv: sv.path.parent.parent
INFO_GENERAL["Session name"] = lambda sv: sv.path.parent.name

INFO_QP = collections.OrderedDict()
INFO_QP["Duration [s]"] = lambda sv: np.ptp(sv.get_times(mode="phase"))
INFO_QP["Mean frame rate [Hz]"] = lambda sv: sv.get_frame_rate(mode="phase")
INFO_QP["Frame rate variance [%]"] = lambda sv: sv.get_frame_rate(
    mode="phase", ret_var=True)[1]
INFO_QP["Number of frames"] = lambda sv: sv.get_size(mode="phase")
INFO_QP["Pixel size [µm]"] = lambda sv: sv.get_meta(mode="phase")[
    "pixel size"] * 1e6
INFO_QP["Medium index"] = lambda sv: sv.get_meta(mode="phase")["medium index"]
INFO_QP["Wavelength [nm]"] = lambda sv: sv.get_meta(mode="phase")[
    "wavelength"] * 1e9

INFO_FL = collections.OrderedDict()
INFO_FL["Duration [s]"] = lambda sv: np.ptp(sv.get_times(mode="fluorescence"))
INFO_FL["Mean frame rate [Hz]"] = lambda sv: sv.get_frame_rate(
    mode="fluorescence")
INFO_FL["Frame rate variance [%]"] = lambda sv: sv.get_frame_rate(
    mode="fluorescence", ret_var=True)[1]
INFO_FL["Number of frames"] = lambda sv: sv.get_size(mode="fluorescence")
INFO_FL["Pixel size [µm]"] = lambda sv: sv.get_meta(mode="fluorescence")[
    "pixel size"] * 1e6

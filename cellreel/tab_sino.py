import collections
import multiprocessing as mp
import pkg_resources
import time

import h5py
import numpy as np
from PyQt5 import uic, QtCore, QtWidgets
import pyqtgraph as pg
from pyqtgraph.parametertree import ParameterTree

from . import helper
from .sino import rot
from . import spacing
from .sino.sino_view import SinoView
from .wiz_align import AlignWizard
from .wiz_flcorr import FluorescenceWizard


class LoadThread(QtCore.QThread):
    def __init__(self, sino_view, count, max_count, *args, **kwargs):
        super(LoadThread, self).__init__(*args, **kwargs)
        self.sino_view = sino_view
        self.kw = {"count": count, "max_count": max_count}

    def run(self):
        self.sino_view.load(**self.kw)


class SinoWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super(SinoWidget, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename("cellreel", "tab_sino.ui")
        uic.loadUi(path_ui, self)

        for vim in [self.ImageView_sino, self.ImageView_slice]:
            vim.ui.histogram.hide()
            vim.ui.roiBtn.hide()
            vim.ui.menuBtn.hide()
            # disable keyboard shortcuts
            vim.keyPressEvent = lambda _: None
            vim.keyReleaseEvent = lambda _: None

        # toolbox changed
        self.toolBox.currentChanged.connect(self.on_toolbox_changed)

        # sinogram selection
        self.comboBox_sino.currentIndexChanged.connect(self.on_sino_select)

        # Line intervals
        self.LinearRegion_angle = pg.LinearRegionItem([0, 10],
                                                      orientation="horizontal")
        self.LinearRegion_angle.hide()  # only shown on page_rot
        self.LinearRegion_angle.sigRegionChanged.connect(self.on_interval_line)
        self.ImageView_slice.addItem(self.LinearRegion_angle)

        # line/slice selectors
        self.hLine_slice = pg.InfiniteLine(angle=0, movable=True, pen="g")
        self.hLine_slice.sigPositionChanged.connect(self.update_image_slice)

        self.vLine_slice = pg.InfiniteLine(angle=90, movable=True, pen="g")
        self.vLine_slice.sigPositionChanged.connect(self.update_image_slice)

        self.rLine_slice = pg.InfiniteLine(
            angle=0, movable=False, pen="FFFFFF50")
        self.rLine_slice.addMarker("v")

        self.vLine_angle = pg.InfiniteLine(angle=0, movable=True, pen="g")
        self.vLine_angle.sigPositionChanged.connect(self.update_image_angle)

        self.ImageView_sino.addItem(self.rLine_slice)
        self.ImageView_sino.addItem(self.vLine_slice)
        self.ImageView_sino.addItem(self.hLine_slice)
        self.ImageView_slice.addItem(self.vLine_angle)

        # data type selectors
        self.radioButton_pha.toggled.connect(self.update_image_mode)
        self.radioButton_amp.toggled.connect(self.update_image_mode)
        self.radioButton_fl.toggled.connect(self.update_image_mode)

        self.radioButton_sino.toggled.connect(self.update_image_slice)
        self.radioButton_kymo.toggled.connect(self.update_image_slice)

        # play pause button
        self.play_pause_thread = PlayPauseThread(self.vLine_angle)
        self.pushButton_play.toggled.connect(self.on_play_pause)
        self.pushButton_faster.clicked.connect(self.on_play_pause_faster)

        # alignmnet button
        self.pushButton_align.clicked.connect(self.on_align)

        # fluorescence correction button
        self.pushButton_flcorr.clicked.connect(self.on_fluorescence_correction)

        # spacing-construction button
        self.pushButton_new_spacing.clicked.connect(self.on_spacing)

        # rotation buttons
        self.pushButton_rot.clicked.connect(self.on_rotation_save)
        self.pushButton_rot_rm.clicked.connect(self.on_rotation_remove)

        # default properties
        self.imkw = {}
        self.data = SinoView()
        self.current_time = 0  # current time update in update_image_angle

        # sinogram parameters
        self.params_rot = rot.get_default_rotation_params()

        # update drawn interval line ROI
        self.params_rot.child("Roll").sigValueChanged.connect(
            self.on_params_axis)
        self.params_rot.child("Start").sigValueChanged.connect(
            self.on_params_interval)
        self.params_rot.child("End").sigValueChanged.connect(
            self.on_params_interval)

        self.states_rot = collections.OrderedDict()

        tr = ParameterTree(showHeader=False)
        tr.setParameters(self.params_rot, showTop=False)
        self.verticalLayout_rotation.insertWidget(3, tr)
        tr.setMaximumSize(184, 16777215)

        # state comboboxes
        self.comboBox_rot.currentTextChanged.connect(self.on_rotation_select)

    @property
    def current_mode(self):
        """Current imaging modality (phase, amplitude, or fluorescence)"""
        if self.radioButton_pha.isChecked():
            return "phase"
        elif self.radioButton_amp.isChecked():
            return "amplitude"
        else:
            return "fluorescence"

    @property
    def current_sino(self):
        """Current sinogram according to `self.current_mode`"""
        data = self.data.get_data(mode=self.current_mode)
        return data

    def load(self, path=None):
        """Load session data"""
        if path is not None:
            self.path = path

        # load sinogram
        self.sinogram_paths = get_sinograms(self.path)
        for cb in [self.comboBox_align, self.comboBox_sino]:
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(list(self.sinogram_paths.keys()))
            cb.setCurrentIndex(len(self.sinogram_paths)-1)
            cb.blockSignals(False)
        self.load_sinogram()

        # load rotation states
        new_states = rot.load_rotation_states(self.path)
        self.states_rot = new_states
        self.update_rotation_dropdown()
        if new_states:
            name1 = list(self.states_rot.keys())[0]
            self.on_rotation_select(name1)
        # update all parameters shown
        self.update_lines()
        self.update_image_mode()

        # hide/disable unused widgets
        if self.data.has_fli():
            self.radioButton_fl.show()
            self.pushButton_flcorr.show()
        else:
            self.radioButton_fl.hide()
            self.pushButton_flcorr.hide()

    def load_sinogram(self):
        """Load sinogram data as defined in `self.comboBox_sino`"""
        self.pushButton_play.setChecked(False)
        name = self.comboBox_sino.currentText()
        self.data.path = self.sinogram_paths[name]
        count = mp.Value('I', 0, lock=True)
        max_count = mp.Value('I', 0, lock=True)

        # self.data.load()
        loadthread = LoadThread(sino_view=self.data,
                                count=count,
                                max_count=max_count)
        loadthread.start()

        bar = QtWidgets.QProgressDialog("Loading data...",
                                        "This button does nothing",
                                        count.value,
                                        max_count.value)
        bar.setCancelButton(None)
        bar.setMinimumDuration(0)
        bar.setAutoClose(True)
        bar.setWindowTitle("Initialization")

        # Show a progress until computation is done
        while count.value == 0 or count.value < max_count.value:
            time.sleep(.05)
            bar.setValue(count.value)
            bar.setMaximum(max_count.value)
            QtCore.QCoreApplication.instance().processEvents()

        # make sure the thread finishes
        loadthread.wait()

    def on_align(self):
        """Let user perform sinogram displacement alignment"""
        self.setEnabled(False)
        name = "Aligned {}"
        pname = "sinogram_{}.h5"
        ii = 0
        while True:
            ii += 1
            sino_name = name.format(ii)
            sino_path = self.path / pname.format(ii)
            if sino_name in self.sinogram_paths:
                continue
            elif sino_path.exists():
                continue
            else:
                break
        self.align_wizard = AlignWizard(name=sino_name,
                                        data=self.data,
                                        path_out=sino_path)
        if self.align_wizard.exec_():
            self.load(self.path)
        self.setEnabled(True)

    def on_fluorescence_correction(self):
        """Let user perform fluorescence correction"""
        self.setEnabled(False)
        name = self.comboBox_align.currentText() + " B {}"
        pname = "sinogram_{}.h5"
        ii = 0
        while True:
            ii += 1
            sino_name = name.format(ii)
            sino_path = self.path / pname.format(ii)
            if sino_name in self.sinogram_paths:
                continue
            elif sino_path.exists():
                continue
            else:
                break
        self.flcorr_wizard = FluorescenceWizard(name=sino_name,
                                                data=self.data,
                                                path_out=sino_path)
        if self.flcorr_wizard.exec_():
            self.load(self.path)
        self.setEnabled(True)

    def on_interval_line(self):
        """User changed rotation interval lines; update self.params_rot"""
        start, end = self.LinearRegion_angle.getRegion()
        t_start, t_end = self.data.convert_index_to_time([start, end],
                                                         self.current_mode)
        self.params_rot.child("Start").setValue(t_start)
        self.params_rot.child("End").setValue(t_end)

    def on_params_axis(self):
        """User changed rotation axis roll param; update GUI lines"""
        angle = self.params_rot.child("Roll").value()
        self.rLine_slice.setAngle(angle)
        self.hLine_slice.setAngle(angle)
        self.vLine_slice.setAngle(angle+90)
        self.update_image_slice()

    def on_params_interval(self):
        """User changed rotation interval param; update GUI lines"""
        t_start = self.params_rot["Start"]
        t_end = self.params_rot["End"]
        start, end = self.data.convert_time_to_index([t_start, t_end],
                                                     self.current_mode)
        self.LinearRegion_angle.blockSignals(True)
        self.LinearRegion_angle.setRegion((start, end))
        self.LinearRegion_angle.blockSignals(False)
        self.update_play_pause_thread_data()

    def on_play_pause(self):
        """User pressed play/pause sinogram video button"""
        self.update_play_pause_thread_data()
        if self.play_pause_thread.isRunning():
            self.play_pause_thread.play = False
            self.play_pause_thread.mult = 1
            self.play_pause_thread.exit()
        else:
            self.play_pause_thread.play = True
            self.play_pause_thread.start()

    def on_play_pause_faster(self):
        self.play_pause_thread.mult *= 1.5

    def on_rotation_select(self, name=None):
        """User selected new rotation state; load and display it"""
        if name is None:
            name = self.comboBox_rot.currentText()
        if name in self.states_rot:
            self.params_rot.restoreState(self.states_rot[name])
            self.lineEdit_rot.setText(name)
            self.comboBox_rot.blockSignals(True)
            self.comboBox_rot.setCurrentIndex(0)
            self.comboBox_rot.blockSignals(False)

    def on_rotation_remove(self):
        """User pressed "Save Rotation" button"""
        name = self.lineEdit_rot.text()
        if name in self.states_rot:
            self.states_rot.pop(name)
            rot.save_rotation_states(path=self.path,
                                     state_dict=self.states_rot)
        self.update_rotation_dropdown()

    def on_rotation_save(self):
        """User pressed "Save Rotation" button"""
        name = self.lineEdit_rot.text()
        state = self.params_rot.saveState()
        self.states_rot[name] = state
        rot.save_rotation_states(path=self.path, state_dict=self.states_rot)
        self.update_rotation_dropdown()

    def on_sino_select(self):
        """User selected new sinogram; load it and update GUI"""
        # load sinogram data
        self.load_sinogram()
        # update lines and parameters
        self.update_lines()
        self.update_image_mode()

    def on_spacing(self):
        # get sinogram data
        slicekw = {"position": self.vLine_slice.pos(),
                   "angle": self.rLine_slice.angle}
        t_start = self.params_rot["Start"]
        t_end = self.params_rot["End"]
        self.spacingWindow = spacing.Spacing(self,
                                             sv=self.data,
                                             slicekw=slicekw,
                                             t_start=t_start,
                                             t_end=t_end,
                                             )
        self.spacingWindow.exec_()
        # update spacing selection
        sp = rot.load_spacing_states(self.path)
        rp = rot.get_default_rotation_params()
        default = rp.child("Spacing").opts["limits"]
        new = sorted(sp.keys())
        self.params_rot.child("Spacing").setLimits(default + new)

    def on_toolbox_changed(self):
        """User changed tool; trigger user-convenience actions"""
        curpage = self.toolBox.currentWidget().objectName()
        if curpage == "page_rot":
            self.LinearRegion_angle.show()
        else:
            self.LinearRegion_angle.hide()
        self.update_play_pause_thread_data()

    def update_image_angle(self):
        """Display the sinogram image defined by `self.vLine_angle`"""
        idx = int(self.vLine_angle.value())
        self.ImageView_sino.setImage(self.current_sino[idx], **self.imkw)
        self.current_time = self.data.get_times(self.current_mode)[idx]
        self.label_time.setText("{:.2f} s".format(self.current_time))
        self.label_frame.setText("{}".format(idx))

    def update_image_slice(self):
        """Display the sinogram slice defined by `v`- or `hLine_slice`"""
        if self.radioButton_sino.isChecked():
            self.vLine_slice.show()
            self.hLine_slice.hide()
            angle = self.rLine_slice.angle
            position = self.vLine_slice.pos()
        else:
            self.vLine_slice.hide()
            self.hLine_slice.show()
            angle = self.rLine_slice.angle + 90
            position = self.hLine_slice.pos()
        image = self.data.get_slice(position=position,
                                    angle=angle,
                                    data=self.current_sino)
        self.ImageView_slice.setImage(image, **self.imkw)

    def update_image_mode(self):
        """User changed imaging modality; Set colors, limits, etc."""
        mode = self.current_mode
        # set colormap
        if mode == "phase":
            cmap = "coolwarm"
        elif mode == "amplitude":
            cmap = "gray"
        else:
            cmap = "YlGnBu_r"

        self.ImageView_sino.setColorMap(helper.get_cmap(name=cmap))
        self.ImageView_slice.setColorMap(helper.get_cmap(name=cmap))

        self.imkw = dict(autoLevels=False,
                         levels=(self.current_sino.min(),
                                 self.current_sino.max())
                         )
        # update self.vLine_angle to match current time
        idx = np.argmin(np.abs(self.current_time-self.data.get_times(mode)))
        self.vLine_angle.setBounds((0, self.current_sino.shape[0]-1))
        self.vLine_angle.setValue(idx)

        self.update_image_angle()
        self.update_image_slice()

        # set frame-rate for playback
        self.update_play_pause_thread_data()
        # update interval for playback
        self.on_toolbox_changed()
        self.update_line_angle_limits()

    def update_line_angle_limits(self):
        """Update the bounding limits of the angle selection lines"""
        self.vLine_angle.setBounds((0, self.current_sino.shape[0]-1))
        self.LinearRegion_angle.blockSignals(True)
        self.LinearRegion_angle.setBounds((0, self.current_sino.shape[0]))
        self.on_params_interval()
        self.LinearRegion_angle.blockSignals(False)

    def update_lines(self):
        """Update all lines and set sane default params for rotation End"""
        # update all widgets
        if self.params_rot["End"] == 0:
            times = self.data.get_times(mode=self.current_mode)
            frame_rate = self.data.get_frame_rate(mode=self.current_mode)
            self.params_rot["End"] = times[-1] + 1 / frame_rate

        self.update_line_angle_limits()

        for line in [self.vLine_slice, self.rLine_slice, self.hLine_slice]:
            line.setValue([self.data.pha.shape[2]//2,
                           self.data.pha.shape[1]//2])
        self.vLine_angle.setValue(0)

    def update_play_pause_thread_data(self):
        times = self.data.get_times(mode=self.current_mode)
        frame_rate = self.data.get_frame_rate(mode=self.current_mode)
        if self.LinearRegion_angle.isVisible():
            self.play_pause_thread.interval_start = self.params_rot["Start"]
            self.play_pause_thread.interval_end = self.params_rot["End"]
        else:
            self.play_pause_thread.interval_start = times[0]
            self.play_pause_thread.interval_end = times[-1]
        self.play_pause_thread.frame_rate = frame_rate
        # set t0 for playback
        self.play_pause_thread.t0 = times[0]

    def update_rotation_dropdown(self):
        """Using `self.states_rot`, populate `self.comboBox_rot`"""
        keys = list(self.states_rot.keys())
        self.comboBox_rot.blockSignals(True)
        self.comboBox_rot.clear()
        self.comboBox_rot.addItems(["Load Rotation..."] + keys)
        self.comboBox_rot.blockSignals(False)


class PlayPauseThread(QtCore.QThread):
    def __init__(self, slider, *args, **kwargs):
        super(PlayPauseThread, self).__init__(*args, **kwargs)
        self.play = True
        self.slider = slider
        #: initial time of the current sinogram data
        self.t0 = 0
        #: play interval start
        self.interval_start = 2.1
        #: play interval end
        self.interval_end = 5.0
        #: playback frame rate [Hz]
        self.frame_rate = 10
        #: playback frame rate multiplier
        self.mult = 1

    def run(self):
        while True:
            if self.play:
                sleep_time = 1/self.frame_rate/self.mult
                if sleep_time < .007:  # set sleep limit
                    sleep_time = .007
                time.sleep(sleep_time)
                val = np.floor(self.slider.value() + 1)
                ctime = val / self.frame_rate + self.t0
                if ctime >= self.interval_end or ctime < self.interval_start:
                    val = (self.interval_start - self.t0) * self.frame_rate
                self.slider.setValue(val)
            else:
                break


def get_sinograms(path):
    """Return a dictionary of sinogram paths for a CellReel session

    Format: {name: path, ...}
    """
    data = [["Raw Sinogram", path / "sinogram.h5", 0]]

    for pp in path.glob("sinogram_*.h5"):
        with h5py.File(pp, mode="r") as h5:
            name = h5.attrs["name"]
            ptime = pp.stat().st_mtime
        data.append([name, pp, ptime])

        data = sorted(data, key=lambda x: x[2])

    odict = collections.OrderedDict()
    for name, pp, _ in data:
        odict[name] = pp
    return odict

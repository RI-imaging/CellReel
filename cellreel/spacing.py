import pkg_resources

import numpy as np
from PyQt5 import uic, QtWidgets
import pyqtgraph as pg

from . import helper
from .sino import rot


class Spacing(QtWidgets.QDialog):
    """Construct New Spacing"""

    def __init__(self, parent, sv, slicekw, t_start, t_end, *args, **kwargs):
        super(Spacing, self).__init__(parent, *args, **kwargs)
        path_ui = pkg_resources.resource_filename("cellreel", "spacing.ui")
        uic.loadUi(path_ui, self)
        self.parent = parent
        # parameters
        self.sv = sv
        self.slicekw = slicekw
        self.t_start = t_start
        self.t_end = t_end
        self.scale = 1
        self.slice = slice(0, -1)
        self.previous_mode = "none"  # set in self.on_mode
        # image views
        self.imageView.ui.roiBtn.hide()
        self.imageView.ui.menuBtn.hide()
        self.imageView.setColorMap(helper.get_cmap(name="viridis"))
        # polylineROI for fitting
        self.line = pg.PolyLineROI([], closed=False)
        self.imageView.addItem(self.line)
        self.line.sigRegionChangeFinished.connect(self.update_fit)
        # plot for line plotting
        self.fit = pg.PlotDataItem()
        self.imageView.addItem(self.fit)
        # signals
        self.horizontalSlider.valueChanged.connect(self.plot_image)
        self.radioButton_pha.clicked.connect(self.on_mode)
        self.radioButton_amp.clicked.connect(self.on_mode)
        self.radioButton_fl.clicked.connect(self.on_mode)
        self.imageView.scene.sigMouseClicked.connect(self.on_add_point)
        self.pushButton.clicked.connect(self.on_save)
        self.pushButton_rm.clicked.connect(self.on_remove)
        self.comboBox.currentIndexChanged.connect(self.on_load)
        self.spinBox.valueChanged.connect(self.update_fit)
        # init
        self.horizontalSlider.setMaximum(self.sv.amp.shape[1])
        self.horizontalSlider.setValue(self.sv.amp.shape[1]//2)
        self.on_mode()
        self.plot_image()
        self.update_spacing_list()

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
        data = self.sv.get_data(mode=self.current_mode)
        idslice = self.sv.get_time_slice(self.t_start, self.t_end,
                                         mode=self.current_mode)
        self.slice = idslice
        return data[idslice]

    def get_points(self, correct_scale=True):
        """Return the current spacing points

        The parameter `correct_scale` defines whether the points
        should be converted to the correct pixel coordinates in
        the original image (defaults to `True`). If this is set to
        `False`, then the scaled coordinates (for visualization
        with pyqtgraph) will be returned.

        See Also
        --------
        self.set_points
        """
        points = [tuple(h.pos()) for h in self.line.getHandles()]
        if correct_scale:
            points = [(p[0]/self.scale, p[1]/self.frame_rate) for p in points]
        return points

    def on_add_point(self, evt):
        """Add a point to `self.line` when user clicks on plot"""
        if evt.accepted:
            return
        view = self.imageView.getView()
        newpos = view.mapSceneToView(evt.pos())
        points = self.get_points(correct_scale=False)
        points.append((newpos.x(), newpos.y()))
        self.set_points(points)
        self.update_fit()

    def on_load(self):
        """Load a user spacing and update all controls"""
        # TODO: check for matching t_start and t_end
        key = self.comboBox.currentText()
        sp = rot.load_spacing_states(path=self.sv.path.parent)
        if key in sp:
            self.spinBox.setValue(sp[key]["num_skw"])
            # set user mode
            mode = sp[key]["user_mode"]
            if mode == "fluorescence":
                if not self.radioButton_fl.isChecked():
                    self.radioButton_fl.toggle()
            elif mode == "phase":
                if not self.radioButton_pha.isChecked():
                    self.radioButton_pha.toggle()
            else:
                if not self.radioButton_amp.isChecked():
                    self.radioButton_amp.toggle()
            self.horizontalSlider.setValue(sp[key]["user_slice"])
            # set title
            self.lineEdit.setText(key)
            # add points
            self.set_points(sp[key]["points"], apply_scale=True)
        # reset combobox
        self.update_spacing_list()
        self.update_fit()

    def on_mode(self):
        """Update the image because the user changed the mode"""
        points = np.array(self.get_points(correct_scale=True))
        self.plot_image()
        if points.size:
            self.set_points(points, apply_scale=True)
            self.update_fit()

    def on_remove(self):
        """Save a user spacing including a wealth of meta data"""
        name = self.lineEdit.text()
        sp = rot.load_spacing_states(path=self.sv.path.parent)
        if name in sp:
            sp.pop(name)
            rot.save_spacing_states(path=self.sv.path.parent,
                                    save_dict=sp)
            self.update_spacing_list()

    def on_save(self):
        """Save a user spacing including a wealth of meta data"""
        image = self.sv.get_slice(data=self.current_sino, **self.slicekw)
        rot.save_spacing_state(path=self.sv.path.parent,
                               name=self.lineEdit.text(),
                               points=self.get_points(correct_scale=True),
                               num_skw=self.spinBox.value(),
                               period=self.t_end - self.t_start,
                               y0=image.shape[1]/2,
                               # time of first frame (user_mode sino)
                               t0=self.t0,
                               t_start=self.t_start,  # interval start
                               t_end=self.t_end,  # interval end
                               user_slice=self.horizontalSlider.value(),
                               user_mode=self.current_mode)
        self.update_spacing_list()
        self.update_fit()

    def plot_image(self):
        """Compute and plot the current sinogram slice"""
        val = self.horizontalSlider.value()
        offset = val - self.current_sino.shape[1]/2
        if self.current_mode == "amplitude":
            fillval = 1
        else:
            fillval = 0
        image = self.sv.get_slice(data=self.current_sino,
                                  offset=offset,
                                  fillval=fillval,
                                  **self.slicekw)
        self.scale = image.shape[0]/image.shape[1]
        self.frame_rate = self.sv.get_frame_rate(mode=self.current_mode)
        self.t0 = self.sv.get_times(mode=self.current_mode)[self.slice.start]
        self.imageView.setImage(image,
                                # square aspect ratio
                                # (this affects getPos and the fit-amplitude)
                                scale=(self.scale, 1),
                                )

    def set_points(self, points, apply_scale=False):
        """Set the current points

        The parameter `apply_scale` defines whether the points should
        be scaled to the image coordinates of pyqtgraph.
        """
        points = sorted(points, key=lambda x: x[1])
        if apply_scale:
            points = [(p[0]*self.scale, p[1]*self.frame_rate) for p in points]
        self.line.blockSignals(True)
        self.line.clearPoints()
        self.line.setPoints(points)
        self.line.blockSignals(False)

    def update_fit(self):
        """Update the plot of the fit (`self.fit`)"""
        points = np.array(self.get_points(correct_scale=True))
        length = self.current_sino.shape[0]/self.frame_rate
        image = self.sv.get_slice(data=self.current_sino, **self.slicekw)
        try:
            func, _ = rot.fit_skewed_periodic(x=points[:, 1],
                                              y=points[:, 0],
                                              period=length,
                                              y0=image.shape[1]/2,
                                              num_skw=self.spinBox.value())
        except (TypeError, ValueError, IndexError):
            pass
        else:
            tslice = self.sv.get_time_slice(self.t_start, self.t_end,
                                            mode=self.current_mode)
            xp = self.sv.get_times(mode=self.current_mode)[tslice] - self.t0
            yp = func(xp)
            self.fit.setData(yp*self.scale, xp*self.frame_rate)
            # call plot again (workaround b/c image is drawn incorrectly)
            self.plot_image()

    def update_spacing_list(self):
        self.comboBox.blockSignals(True)
        sp = rot.load_spacing_states(path=self.sv.path.parent)
        self.comboBox.clear()
        self.comboBox.addItems(["Load..."] + list(sp.keys()))
        self.comboBox.blockSignals(False)

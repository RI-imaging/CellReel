import collections
import multiprocessing as mp
import pkg_resources
import time

import h5py
from PyQt5 import uic, QtWidgets, QtCore

from . import crosshair, helper
from .reco import fl_algs, post_algs, ri_algs
from .sino import rot
from .sino.sino_view import SinoView
from .tab_sino import get_sinograms

from ._version import version


class RecoWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super(RecoWidget, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename("cellreel", "tab_reco.ui")
        uic.loadUi(path_ui, self)

        for vim in [self.imageView_ri, self.imageView_fl]:
            # vim.ui.histogram.hide()
            vim.ui.roiBtn.hide()
            vim.ui.menuBtn.hide()
            # disable keyboard shortcuts
            vim.keyPressEvent = lambda _: None
            vim.keyReleaseEvent = lambda _: None

        self.imageView_ri.setColorMap(helper.get_cmap(name="gnuplot2"))
        self.imageView_fl.setColorMap(helper.get_cmap(name="YlGnBu_r"))

        # add crosshair
        self.crosshair = crosshair.CrossHairTwin(self.imageView_ri,
                                                 self.imageView_fl,
                                                 self.update_ri_fl_labels)

        # dataset selection
        self.comboBox_reco.currentIndexChanged.connect(self.update_data)
        self.verticalSlider.valueChanged.connect(self.update_image)

        # compute button
        self.pushButton_compute.clicked.connect(self.on_compute)

        # slice selectors
        self.radioButton_xy.toggled.connect(self.on_change_slice)
        self.radioButton_xz.toggled.connect(self.on_change_slice)
        self.radioButton_yz.toggled.connect(self.on_change_slice)

        # reconstruction methods
        self.comboBox_alg.clear()
        self.comboBox_alg.addItems(list(ri_algs.keys()))
        self.comboBox_alg.setCurrentIndex(0)

        # post-processing methods
        self.comboBox_post.clear()
        self.comboBox_post.addItems(list(post_algs.keys()))
        self.comboBox_post.setCurrentIndex(0)

        # defaults
        self._initialize_views = True
        self.recos = {}
        self.h5file = None
        self.data_ri = None
        self.data_fl = None
        self.progressBar_fl.hide()
        self.progressBar_ri.hide()
        self.progressBar_post.hide()

    def compute_fl(self, path_out, sv, rotation_name):
        """Fluorescence tomography reconstruction"""
        count = mp.Value('I', 0, lock=True)
        max_count = mp.Value('I', 0, lock=True)

        runkw = {"scheme": "standard",
                 "count_rec": count,
                 "max_count_rec": max_count,
                 }

        reclass = fl_algs["BPJ (radontea)"]
        recinst = reclass(sv=sv, rotation_name=rotation_name)

        recothread = RecoThread(recinst=recinst, runkw=runkw)
        recothread.start()

        # Show a progress until computation is done
        while count.value == 0 or count.value < max_count.value:
            time.sleep(.01)
            self.progressBar_fl.setMaximum(max_count.value)
            self.progressBar_fl.setValue(count.value)
            QtCore.QCoreApplication.instance().processEvents()
        self.progressBar_fl.setMaximum(max_count.value)
        self.progressBar_fl.setValue(count.value)

        # make sure the thread finishes
        recothread.wait()

        rec, info = recothread.result

        # save reconstruction
        angles, angle_slice = recinst.get_angles_slice(mode="fluorescence")
        with h5py.File(path_out, mode="a") as h5:
            ds = h5.create_dataset("fluorescence",
                                   data=rec,
                                   chunks=True,
                                   fletcher32=True,
                                   )
            rot = h5.require_group("rotation")
            rds = rot.create_dataset("fluorescence", data=angles)
            rds.attrs["sinogram start"] = angle_slice.start
            rds.attrs["sinogram stop"] = angle_slice.stop
            for key in info:
                ds.attrs[key] = info[key]

    def compute_ri(self, path_out, sv, rotation_name):
        """Refractive index reconstruction"""
        count_rec = mp.Value('I', 0, lock=True)
        max_count_rec = mp.Value('I', 0, lock=True)
        count_pp = mp.Value('I', 0, lock=True)
        max_count_pp = mp.Value('I', 0, lock=True)

        scheme = self.comboBox_scheme.currentText()
        applecorr = post_algs[self.comboBox_post.currentText()]
        kwargs = {"save_memory": not self.checkBox_ram.isChecked()}

        runkw = {"scheme": scheme,
                 "apple_core_correction": applecorr,
                 "count_rec": count_rec,
                 "max_count_rec": max_count_rec,
                 "count_pp": count_pp,
                 "max_count_pp": max_count_pp,
                 }

        reclass = ri_algs[self.comboBox_alg.currentText()]
        recinst = reclass(sv=sv,
                          rotation_name=rotation_name,
                          kwargs=kwargs)

        recothread = RecoThread(recinst=recinst, runkw=runkw)
        recothread.start()

        # Show progress until computation is done
        while count_rec.value == 0 or count_rec.value < max_count_rec.value:
            time.sleep(.01)
            self.progressBar_ri.setMaximum(max_count_rec.value)
            self.progressBar_ri.setValue(count_rec.value)
            QtCore.QCoreApplication.instance().processEvents()
        self.progressBar_ri.setMaximum(max_count_rec.value)
        self.progressBar_ri.setValue(count_rec.value)
        QtCore.QCoreApplication.instance().processEvents()

        if applecorr:
            while count_pp.value == 0 or count_pp.value < max_count_pp.value:
                time.sleep(.01)
                self.progressBar_post.setMaximum(max_count_pp.value)
                self.progressBar_post.setValue(count_pp.value)
                QtCore.QCoreApplication.instance().processEvents()
            self.progressBar_post.setMaximum(max_count_pp.value)
            self.progressBar_post.setValue(count_pp.value)
            QtCore.QCoreApplication.instance().processEvents()

        # make sure the thread finishes
        recothread.wait()

        ri, info = recothread.result

        # save reconstruction
        angles, angle_slice = recinst.get_angles_slice(mode="phase")
        with h5py.File(path_out, mode="a") as h5:
            ds = h5.create_dataset("refractive_index",
                                   data=ri,
                                   chunks=True,
                                   fletcher32=True,
                                   )

            rot = h5.require_group("rotation")
            rds = rot.create_dataset("refractive_index", data=angles)
            rds.attrs["sinogram start"] = angle_slice.start
            rds.attrs["sinogram stop"] = angle_slice.stop
            for key in info:
                ds.attrs[key] = info[key]

    def load(self, path=None):
        """Make available all session data"""
        if path is not None:
            self.path = path
        # get available reconstructions
        self.recos = get_reconstructions(self.path)
        self.comboBox_reco.blockSignals(True)
        self.comboBox_reco.clear()
        if self.recos:
            self.comboBox_reco.addItems(list(self.recos.keys()))
            self.comboBox_reco.blockSignals(False)
            self.comboBox_reco.setCurrentIndex(len(self.recos)-1)
        else:
            self.comboBox_reco.blockSignals(False)

        # Set default name for new reconstruction
        name = "Rec {}"
        ii = 0
        while True:
            ii += 1
            rname = name.format(len(self.recos)+ii)
            if rname not in self.recos:
                break
        self.lineEdit_reco.setText(rname)
        self.update_data()

        if self.data_fl is not None and self.data_ri is not None:
            # link views for RI and FL
            # (we need to test for existence of both data types,
            # otherwise for RI-only data the initial view is screwed up)
            view_ri = self.imageView_ri.getView()
            view_fl = self.imageView_fl.getView()
            view_ri.linkView(view=view_fl, axis=self.imageView_fl.view.XAxis)
            view_ri.linkView(view=view_fl, axis=self.imageView_fl.view.YAxis)

        # Switch to compute tab if no reconstruction is available
        if self.recos:
            self.toolBox.setCurrentIndex(0)
        else:
            self.toolBox.setCurrentIndex(1)

        # hide/disable unused widgets
        if self.data_fl is None:
            self.checkBox_fl.hide()
            self.checkBox_ri.hide()
            self.imageView_fl.hide()
        else:
            self.checkBox_fl.show()
            self.checkBox_ri.show()
            self.imageView_fl.show()

    def on_change_slice(self):
        """Switch between x-y-z visualization"""
        if self.radioButton_xy.isChecked():
            size = self.data_ri.shape[2]
        elif self.radioButton_xz.isChecked():
            size = self.data_ri.shape[1]
        else:
            size = self.data_ri.shape[0]

        self.verticalSlider.blockSignals(True)
        self.verticalSlider.setMaximum(size - 1)
        if self._initialize_views:
            self.verticalSlider.setValue(size // 2)
        self.verticalSlider.blockSignals(False)
        self.update_image()

    def on_compute(self):
        """Perform multimodal tomographic reconstruction"""
        self.widget_compute.setDisabled(True)
        sinograms = get_sinograms(self.path)
        path_in = sinograms[self.comboBox_align.currentText()]
        sv = SinoView(path_in).load()

        if sv.has_qpi():
            self.progressBar_ri.show()
            if post_algs[self.comboBox_post.currentText()] is not None:
                # only show post-processing progress bar if it is selected
                self.progressBar_post.show()
        if sv.has_fli():
            self.progressBar_fl.show()
        QtCore.QCoreApplication.instance().processEvents()
        # get rotation parameters
        rotation_name = self.comboBox_rot.currentText()

        name = "reconstruction_{}.h5"
        ii = 0
        while True:
            ii += 1
            path_out = self.path / name.format(len(self.recos)+ii)
            if not path_out.exists():
                break

        t_init = time.time()

        with h5py.File(path_out, mode="a") as h5:
            h5.attrs["name"] = self.lineEdit_reco.text()

        if sv.has_fli():
            self.compute_fl(path_out=path_out,
                            sv=sv,
                            rotation_name=rotation_name)

        if sv.has_qpi():
            self.compute_ri(path_out=path_out,
                            sv=sv,
                            rotation_name=rotation_name)

        states = rot.load_rotation_states(self.path)
        state_rot = states[rotation_name]["children"]

        with h5py.File(path_out, "a") as h5:
            h5.attrs["sinogram hash"] = sv.get_hash()
            h5.attrs["rotation hash"] = rot.get_hash(self.path, rotation_name)
            h5.attrs["wavelength"] = sv.meta["wavelength"],
            h5.attrs["pixel size"] = sv.meta["pixel size"],
            h5.attrs["medium index"] = sv.meta["medium index"],
            h5.attrs["reconstruction time"] = time.time() - t_init
            h5.attrs["CellReel version"] = version
            scheme = self.comboBox_scheme.currentText()
            h5.attrs["reconstruction scheme"] = scheme

            grot = h5.require_group("rotation")
            for ch in state_rot:
                grot.attrs[ch] = state_rot[ch]["value"]

        # reload view
        self.load(self.path)
        self.progressBar_fl.hide()
        self.progressBar_ri.hide()
        self.progressBar_post.hide()
        self.widget_compute.setEnabled(True)
        self.progressBar_fl.setValue(0)
        self.progressBar_ri.setValue(0)
        self.progressBar_post.setValue(0)

    def update_ri_fl_labels(self, ri, fl):
        self.label_ri.setText("{:.5f}".format(ri))
        self.label_fl.setText("{:.2f}".format(fl))

    def update_image(self):
        """Show selected slice image"""
        val = self.verticalSlider.value()
        for data, view, in zip([self.data_ri, self.data_fl],
                               [self.imageView_ri, self.imageView_fl],
                               ):
            if data is not None:
                if self.radioButton_xy.isChecked():
                    aslice = data[:, :, val].real
                elif self.radioButton_xz.isChecked():
                    aslice = data[:, val, :].real
                else:
                    aslice = data[val, :, :].real
                view.setImage(aslice,
                              autoLevels=False,
                              autoHistogramRange=False)
                # remove colored ticks from colorbar
                for tick in list(view.ui.histogram.gradient.ticks):
                    tick.hide()

    def update_sino_data(self):
        """Update combobox selection for alignment and rotation

        Triggered when main tab changed
        """
        self.comboBox_align.clear()
        sinograms = get_sinograms(self.path)
        self.comboBox_align.addItems(list(sinograms.keys()))
        self.comboBox_align.setCurrentIndex(len(sinograms)-1)
        self.comboBox_rot.clear()
        states_rot = rot.load_rotation_states(self.path)
        if states_rot:
            self.comboBox_rot.addItems(list(states_rot.keys()))
            self.comboBox_rot.setCurrentIndex(len(states_rot)-1)
            self.pushButton_compute.setEnabled(True)
        else:
            # user has to create rotation first
            self.comboBox_rot.addItems(["No rotation defined!"])
            self.pushButton_compute.setEnabled(False)

    def update_data(self):
        """Initialize visualization of reconstructed data"""
        self.data_ri = None
        self.data_fl = None
        if not self.recos:
            return
        path = self.recos[self.comboBox_reco.currentText()]
        if self.h5file is not None:
            self.h5file.close()
        self.h5file = h5py.File(path, mode="r")
        attrs = self.h5file.attrs
        # reset labels
        for ll in [self.label_alg, self.label_opts, self.label_rot,
                   self.label_sino, self.label_time]:
            ll.setText("-")
        opts = []
        if "reconstruction scheme" in attrs:
            opts.append(attrs["reconstruction scheme"])
        if "sinogram hash" in attrs:
            self.label_sino.setText(attrs["sinogram hash"][:5])
        if "rotation hash" in attrs:
            self.label_rot.setText(attrs["rotation hash"][:5])
        if "reconstruction time" in attrs:
            self.label_time.setText("{:.0f} s".format(
                attrs["reconstruction time"]))
        if "refractive_index" in self.h5file:
            self.data_ri = self.h5file["refractive_index"]
            riattrs = self.data_ri.attrs
            if "algorithm" in riattrs:
                self.label_alg.setText("{}\n({})".format(riattrs["algorithm"],
                                                         riattrs["library"]))
            if "apple core correction" in riattrs:
                opts.append(riattrs["apple core correction"])

            if self._initialize_views:
                rimin = self.data_ri.attrs["real min"]
                rimax = self.data_ri.attrs["real max"]
                self.imageView_ri.ui.histogram.setHistogramRange(rimin, rimax)
                self.imageView_ri.ui.histogram.setLevels(rimin, rimax)
        if "fluorescence" in self.h5file:
            self.data_fl = self.h5file["fluorescence"]
            if self._initialize_views:
                flmin = self.data_fl.attrs["min"]
                flmax = self.data_fl.attrs["max"]
                self.imageView_fl.ui.histogram.setHistogramRange(flmin, flmax)
                self.imageView_fl.ui.histogram.setLevels(flmin, flmax)
        if opts:
            self.label_opts.setText("\n".join(opts))
        # update slider limits
        if self.data_ri:
            self.on_change_slice()
        # disable initialization
        if self._initialize_views:
            self._initialize_views = False


class RecoThread(QtCore.QThread):
    def __init__(self, recinst, runkw, *args, **kwargs):
        super(RecoThread, self).__init__(*args, **kwargs)
        self.recinst = recinst
        self.runkw = runkw

    def run(self):
        self.result = self.recinst.run(**self.runkw)


def get_reconstructions(path):
    """Return a dictionary of reconstruction paths for a CellReel session

    Format: {name: path, ...}
    """
    data = []

    for pp in path.glob("reconstruction_*.h5"):
        with h5py.File(pp, mode="r") as h5:
            name = h5.attrs["name"]
            ptime = pp.stat().st_mtime
        data.append([name, pp, ptime])
        data = sorted(data, key=lambda x: x[2])

    odict = collections.OrderedDict()
    for name, pp, _ in data:
        odict[name] = pp
    return odict

import os
import pathlib
import pkg_resources
import tempfile
import time

import numpy as np
from PyQt5 import uic, QtWidgets
import pyqtgraph as pg
from pyqtgraph.parametertree import Parameter, ParameterTree
from qpimage.bg_estimate import VALID_FIT_OFFSETS, VALID_FIT_PROFILES
import qpformat

from .. import helper
from . import task_convert
from . import task_simulate
from . import meta_hints
from . import coloc
from . import task_download

# register file formats
from .formats import flformat


ui_pages = ["start.ui",
            "choose_data.ui",
            "dld_data.ui",
            "own_data.ui",
            "own_data_coloc.ui",
            "own_data_bg.ui",
            "art_data.ui",
            ]

final_pages = ["own_data_bg.ui",
               "art_data.ui",
               ]


class InitPage(QtWidgets.QWizardPage):
    """Initial wizard page base"""

    def __init__(self, ui_name, *args, **kwargs):
        super(InitPage, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename("cellreel.wiz_init", ui_name)
        uic.loadUi(path_ui, self)
        self.ui_name = ui_name

    def nextId(self):
        """Reimplementation to allow finishing in arbitrary page"""
        if self.ui_name in final_pages:
            return -1
        else:
            # Fallback to default linear behavior
            return super(InitPage, self).nextId()


class InitPageChooseData(InitPage):
    """Initial wizard page, track switch for user choice"""

    def nextId(self):
        # follow combobox selection
        if self.radioButton_own_data.isChecked():
            return ui_pages.index("own_data.ui")
        elif self.radioButton_artificial.isChecked():
            return ui_pages.index("art_data.ui")
        else:
            return ui_pages.index("dld_data.ui")


class InitPageDownloadData(InitPage):
    """Initial wizard page, track switch for user choice"""

    def __init__(self, *args, **kwargs):
        super(InitPageDownloadData, self).__init__(*args, **kwargs)
        self.dldir = pathlib.Path(os.path.expanduser("~")) / "Downloads"
        self.lineEdit.setText(str(self.dldir))
        self._init_combobox()
        # signals
        self.comboBox.currentTextChanged.connect(self.on_combobox)
        self.pushButton.clicked.connect(self.on_download)

    def _init_combobox(self):
        keys = sorted(task_download.get_available_datasets().keys())
        self.comboBox.clear()
        self.comboBox.addItems(keys)
        self.on_combobox()

    def isComplete(self, *args, **kwargs):
        """Check file sizes to determine whether download is complete"""
        key = self.comboBox.currentText()
        data = task_download.get_available_datasets()[key]
        dest_size = task_download.get_dataset_size(key)
        actu_size = 0
        for dt in data["data"]:
            dpath = (self.dldir / dt["name"])
            if dpath.exists():
                actu_size += dpath.stat().st_size
        if actu_size == dest_size:
            return True
        else:
            return False

    def nextId(self):
        """Reimplementation to allow finishing in arbitrary page"""
        # Fallback to default linear behavior
        return ui_pages.index("own_data.ui")

    def on_combobox(self):
        """User selected new dataset"""
        key = self.comboBox.currentText()
        data = task_download.get_available_datasets()[key]
        self.label_descr.setText(data["descr"])
        size = task_download.get_dataset_size(key)
        self.label_size.setText("{:.0f} MB".format(size/1024**2))
        refs = []
        for r in data["refs"]:
            refs.append("- <a href='{link}'>{link}</a>".format(link=r))
        self.label_refs.setText("<br/>".join(refs))
        files = []
        for dt in data["data"]:
            files.append("- <a href='{}'>{}</a>".format(dt["urls"][0],
                                                        dt["name"]))
        self.label_files.setText("<br/>".join(files))
        self.completeChanged.emit()

    def on_download(self):
        """User wants to download dataset"""
        self.comboBox.setEnabled(False)
        self.pushButton.setEnabled(False)
        self.dldir.mkdir(exist_ok=True)
        key = self.comboBox.currentText()
        task_download.download_dataset_qt5(key=key,
                                           path=self.dldir,
                                           progressbar=self.progressBar)
        self.comboBox.setEnabled(True)
        self.pushButton.setEnabled(True)
        self.completeChanged.emit()

    def validatePage(self):
        """Set all paths in relevant pages"""
        self.dldir.mkdir(exist_ok=True)
        key = self.comboBox.currentText()
        # set the correct paths in the next pages
        pown = self.wizard().page(ui_pages.index("own_data.ui"))
        powncol = self.wizard().page(ui_pages.index("own_data_coloc.ui"))
        for dt in task_download.get_available_datasets()[key]["data"]:
            if dt["dest"] == "reference fli":
                powncol.on_browse_fli(path=self.dldir / dt["name"])
            elif dt["dest"] == "reference qpi":
                powncol.on_browse_qpi(path=self.dldir / dt["name"])
            elif dt["dest"] == "sinogram fli":
                pown.on_data_fl(path=self.dldir / dt["name"])
            elif dt["dest"] == "sinogram qpi":
                pown.on_data_qpi(path=self.dldir / dt["name"])
        return True


class InitPageOwnData(InitPage):
    """Initial wizard page for user data"""

    def __init__(self, *args, **kwargs):
        super(InitPageOwnData, self).__init__(*args, **kwargs)
        # signals
        self.pushButton_data_qpi.clicked.connect(self.on_data_qpi)
        self.pushButton_data_qpi_bg.clicked.connect(self.on_data_qpi_bg)
        self.pushButton_data_fl.clicked.connect(self.on_data_fl)
        # variables
        self.path_data_fl = None
        self.path_data_qpi = None
        self.path_data_qpi_bg = None
        # metadata qpi
        group_meta_qp = [
            {'name': 'wavelength', 'type': 'float', 'value': 550,
             'step': 10, 'decimals': 6, 'suffix': 'nm'},
            {'name': 'pixel size', 'type': 'float', 'value': .134,
             'step': 0.01, 'decimals': 6, 'suffix': 'µm'},
            {'name': 'medium index', 'type': 'float', 'value': 1.335,
             'step': 0.1, 'decimals': 6},
        ]
        self.params_meta_qp = Parameter.create(name='params',
                                               type='group',
                                               children=group_meta_qp)
        tr = ParameterTree(showHeader=False)
        tr.setParameters(self.params_meta_qp, showTop=False)
        self.verticalLayout_qpi.addWidget(tr)
        # metadata fli
        group_meta_fl = [
            {'name': 'pixel size', 'type': 'float', 'value': .134,
             'step': 0.01, 'decimals': 6, 'suffix': 'µm'},
        ]
        self.params_meta_fl = Parameter.create(name='params',
                                               type='group',
                                               children=group_meta_fl)
        tr2 = ParameterTree(showHeader=False)
        tr2.setParameters(self.params_meta_fl, showTop=False)
        self.verticalLayout_fli.addWidget(tr2)

    def nextId(self):
        if self.path_data_fl is None:
            # no need for colocalization
            return ui_pages.index("own_data_bg.ui")
        else:
            return ui_pages.index("own_data_coloc.ui")

    def on_data_fl(self, **kwargs):
        """User selects fluorescence data"""
        if "path" in kwargs and pathlib.Path(kwargs["path"]).exists():
            path = str(kwargs["path"])
        else:
            path = QtWidgets.QFileDialog.getOpenFileName()[0]
        if path:
            self.path_data_fl = pathlib.Path(path)
            self.lineEdit_path_data_fl.setText(path)
            # check meta data
            ds = flformat.load_data(path=path)
            if "pixel size" in ds.meta_data:
                self.params_meta_fl.child("pixel size").setValue(
                    ds.meta_data["pixel size"] * 1e6)

    def on_data_qpi(self, **kwargs):
        """User selects QPI data"""
        if "path" in kwargs and pathlib.Path(kwargs["path"]).exists():
            path = str(kwargs["path"])
        else:
            path = QtWidgets.QFileDialog.getOpenFileName()[0]
        if path:
            self.path_data_qpi = pathlib.Path(path)
            self.lineEdit_path_data_qpi.setText(path)
            # check metadata
            ds = qpformat.load_data(path=path)
            for key, mult in [("pixel size", 1e6),
                              ("wavelength", 1e9),
                              ("medium index", 1)]:
                if key in ds.meta_data:
                    self.params_meta_qp.child(key).setValue(
                        ds.meta_data[key] * mult)
            # set previously stored hints
            hints = meta_hints.load_hints(path_qpi=path)
            for key in "wavelength", "pixel size", "medium index":
                if key in hints:
                    self.params_meta_qp.child(key).setValue(hints[key])
            if "path_qpi_bg" in hints:
                self.on_data_qpi_bg(path=hints["path_qpi_bg"])
            if "path_fl" in hints:
                self.on_data_fl(path=hints["path_fl"])
            if "pixel size fl" in hints:
                self.params_meta_fl.child("pixel size").setValue(
                    hints["pixel size fl"])

    def on_data_qpi_bg(self, **kwargs):
        """User selects QPI background data"""
        if "path" in kwargs and pathlib.Path(kwargs["path"]).exists():
            path = str(kwargs["path"])
        else:
            path = QtWidgets.QFileDialog.getOpenFileName()[0]
        if path:
            self.path_data_qpi_bg = pathlib.Path(path)
            self.lineEdit_path_data_qpi_bg.setText(path)


class InitPageOwnDataBG(InitPage):
    """Init wizard page for user's background correction"""

    def __init__(self, *args, **kwargs):
        super(InitPageOwnDataBG, self).__init__(*args, **kwargs)
        # defaults
        self.ImageView.ui.roiBtn.hide()
        self.ImageView.ui.menuBtn.hide()
        self.ImageView.setColorMap(helper.get_cmap(name="coolwarm"))
        # add ROI selector
        self.roi = pg.RectROI([20, 20], [200, 200], pen=(0, 9))
        self.ImageView.addItem(self.roi)
        # add parameter tree
        group_bg = [
            {'name': 'fit_offset', 'type': 'list',
             'values': VALID_FIT_OFFSETS, 'value': VALID_FIT_OFFSETS[0]},
            {'name': 'fit_profile', 'type': 'list',
             'values': VALID_FIT_PROFILES, 'value': VALID_FIT_PROFILES[2]},
            {'name': 'border_px', 'type': 'int', 'value': 10,
             'step': 1, },
        ]
        self.params = Parameter.create(name='params',
                                       type='group',
                                       children=group_bg)
        tr = ParameterTree(showHeader=False)
        tr.setParameters(self.params, showTop=False)
        tr.setMaximumSize(200, 16777215)
        self.horizontalLayout.addWidget(tr)
        # connect slider event
        self.horizontalSlider.valueChanged.connect(self.on_slider)
        # connect buttons
        self.pushButton_start.clicked.connect(self.on_start)
        self.pushButton_end.clicked.connect(self.on_end)

    def initializePage(self):
        """Load experimental data"""
        wiz = self.wizard()
        pod = wiz.page(ui_pages.index("own_data.ui"))
        self.ds = qpformat.load_data(path=pod.path_data_qpi,
                                     bg_data=pod.path_data_qpi_bg,)
        hints = meta_hints.load_hints(path_qpi=pod.path_data_qpi)
        if "roi pos" in hints:
            self.roi.setPos(hints["roi pos"])
        if "roi size" in hints:
            self.roi.setSize(hints["roi size"])
        if "background correction" in hints:
            for key in hints["background correction"]:
                self.params[key] = hints["background correction"][key]
        if "interval start" in hints:
            self.spinBox_start.setValue(hints["interval start"])
        if "interval end" in hints and hints["interval end"] <= len(self.ds):
            end = hints["interval end"]
        else:
            end = len(self.ds) - 1
        self.spinBox_end.setValue(end)

        self.horizontalSlider.setMinimum(0)
        self.horizontalSlider.setMaximum(len(self.ds) - 1)
        self.horizontalSlider.setValue(0)
        self.on_slider()

    def on_end(self):
        self.spinBox_end.setValue(self.horizontalSlider.value())

    def on_start(self):
        self.spinBox_start.setValue(self.horizontalSlider.value())

    def on_slider(self):
        """Show image defined by `self.horizontalSlider`"""
        idx = self.horizontalSlider.value()
        image = self.ds.get_qpimage(idx).pha
        self.ImageView.setImage(image)


class InitPageOwnDataColoc(InitPage):
    """Init wizard page for user's background correction"""

    def __init__(self, *args, **kwargs):
        super(InitPageOwnDataColoc, self).__init__(*args, **kwargs)
        # defaults
        for imv in [self.ImageView_pha, self.ImageView_amp,
                    self.ImageView_florig, self.ImageView_fl]:
            imv.ui.roiBtn.hide()
            imv.ui.menuBtn.hide()
            imv.ui.histogram.hide()

        self.ImageView_pha.setColorMap(helper.get_cmap(name="coolwarm"))
        self.ImageView_amp.setColorMap(helper.get_cmap(name="gray"))
        self.ImageView_florig.setColorMap(helper.get_cmap(name="YlGnBu_r"))
        self.ImageView_fl.setColorMap(helper.get_cmap(name="YlGnBu_r"))

        # browse buttons
        self.pushButton_browse_fli.clicked.connect(self.on_browse_fli)
        self.pushButton_browse_qpi.clicked.connect(self.on_browse_qpi)
        # position selection buttons
        self.p_qpx.valueChanged.connect(self.on_points_changed)
        self.p_qpy.valueChanged.connect(self.on_points_changed)
        self.p_flx.valueChanged.connect(self.on_points_changed)
        self.p_fly.valueChanged.connect(self.on_points_changed)
        # lines phase
        self.line_ph = pg.InfiniteLine(angle=0, movable=True, pen="g")
        self.line_pv = pg.InfiniteLine(angle=90, movable=True, pen="g")
        self.line_ph.sigPositionChangeFinished.connect(self.on_lines_changed)
        self.line_pv.sigPositionChangeFinished.connect(self.on_lines_changed)
        self.ImageView_pha.addItem(self.line_ph)
        self.ImageView_pha.addItem(self.line_pv)
        # lines amplitude
        self.line_ah = pg.InfiniteLine(angle=0, movable=True, pen="g")
        self.line_av = pg.InfiniteLine(angle=90, movable=True, pen="g")
        self.line_ah.sigPositionChangeFinished.connect(self.on_lines_changed)
        self.line_av.sigPositionChangeFinished.connect(self.on_lines_changed)
        self.ImageView_amp.addItem(self.line_ah)
        self.ImageView_amp.addItem(self.line_av)
        # lines original fluorescennce
        self.line_oh = pg.InfiniteLine(angle=0, movable=True, pen="g")
        self.line_ov = pg.InfiniteLine(angle=90, movable=True, pen="g")
        self.line_oh.sigPositionChangeFinished.connect(self.on_lines_changed)
        self.line_ov.sigPositionChangeFinished.connect(self.on_lines_changed)
        self.ImageView_florig.addItem(self.line_oh)
        self.ImageView_florig.addItem(self.line_ov)
        # lines warped fluorescence
        self.line_fh = pg.InfiniteLine(angle=0, movable=False, pen="y")
        self.line_fv = pg.InfiniteLine(angle=90, movable=False, pen="y")
        self.ImageView_fl.addItem(self.line_fh)
        self.ImageView_fl.addItem(self.line_fv)

        self.path_data_fl = None
        self.path_data_qp = None

    def initializePage(self):
        """Load experimental data"""
        wiz = self.wizard()
        pod = wiz.page(ui_pages.index("own_data.ui"))
        hints = meta_hints.load_hints(path_qpi=pod.path_data_qpi)
        if "coloc qp" in hints:
            self.p_qpx.setValue(hints["coloc qp"][0])
            self.p_qpy.setValue(hints["coloc qp"][1])
        if "coloc fl" in hints:
            self.p_flx.setValue(hints["coloc fl"][0])
            self.p_fly.setValue(hints["coloc fl"][1])
        if "path_reference_qpi" in hints:
            self.on_browse_qpi(path=hints["path_reference_qpi"])
        if "path_reference_fli" in hints:
            self.on_browse_fli(path=hints["path_reference_fli"])

    def on_browse_fli(self, **kwargs):
        if "path" in kwargs:
            path = str(kwargs["path"])
        else:
            path = QtWidgets.QFileDialog.getOpenFileName()[0]
        if path:
            self.path_data_fl = pathlib.Path(path)
            self.lineEdit_path_fli.setText(path)
            self.on_points_changed()

    def on_browse_qpi(self, **kwargs):
        if "path" in kwargs:
            path = str(kwargs["path"])
        else:
            path = QtWidgets.QFileDialog.getOpenFileName()[0]
        if path:
            self.path_data_qp = pathlib.Path(path)
            self.lineEdit_path_qpi.setText(path)
            self.on_points_changed()

    def on_lines_changed(self):
        line = self.sender()
        pos = line.value()
        self.blockSignals(True)
        if line in [self.line_ah, self.line_ph]:
            self.line_ah.setValue(pos)
            self.line_ph.setValue(pos)
            self.line_fh.setValue(pos)
            self.p_qpy.setValue(pos)
        elif line in [self.line_av, self.line_pv]:
            self.line_av.setValue(pos)
            self.line_pv.setValue(pos)
            self.line_fv.setValue(pos)
            self.p_qpx.setValue(pos)
        elif line is self.line_ov:
            self.p_flx.setValue(pos)
        elif line is self.line_oh:
            self.p_fly.setValue(pos)
        self.blockSignals(False)
        self.on_points_changed()

    def on_points_changed(self):
        """Update image colocalization visualization"""
        if self.path_data_fl and self.path_data_qp:
            # colocalization metadata
            colockw = self.wizard().get_coloc_kwargs()
            # get fluorescence image
            fli = flformat.load_data(self.path_data_fl).get_flimage(0)
            # get quantitative phase image
            qpi = qpformat.load_data(self.path_data_qp).get_qpimage(0)
            # get warped fluorescence image
            flc = coloc.warp_fl(fl=fli.fl,
                                output_shape=qpi.shape,
                                **colockw)
            # draw data
            self.ImageView_pha.setImage(qpi.pha)
            self.ImageView_amp.setImage(qpi.amp)
            self.ImageView_florig.setImage(fli.fl)
            self.ImageView_fl.setImage(flc)
            # update lines
            self.blockSignals(True)
            self.line_ah.setValue(colockw["p_qp"][1])
            self.line_ph.setValue(colockw["p_qp"][1])
            self.line_fh.setValue(colockw["p_qp"][1])
            self.line_av.setValue(colockw["p_qp"][0])
            self.line_pv.setValue(colockw["p_qp"][0])
            self.line_fv.setValue(colockw["p_qp"][0])
            self.line_oh.setValue(colockw["p_fl"][1])
            self.line_ov.setValue(colockw["p_fl"][0])
            self.blockSignals(False)


class InitWizard(QtWidgets.QWizard):
    """Initial wizard for data import"""

    def __init__(self, parent=None):
        super(InitWizard, self).__init__(parent)
        self._init_pages()
        self.setWindowTitle("CellReel data initialization")
        self.resize(640, 530)

        self.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self._finalize)

    def _init_pages(self):
        """Initializes all pages with their dedicated logic"""
        for pp in ui_pages:
            if pp == "choose_data.ui":
                page = InitPageChooseData(pp, self)
            elif pp == "own_data.ui":
                page = InitPageOwnData(pp, self)
            elif pp == "own_data_bg.ui":
                page = InitPageOwnDataBG(pp, self)
            elif pp == "own_data_coloc.ui":
                page = InitPageOwnDataColoc(pp, self)
            elif pp == "dld_data.ui":
                page = InitPageDownloadData(pp, self)
            else:
                page = InitPage(pp, self)
            self.addPage(page)

    def _finalize(self):
        """Trigger data import task with data from wizard pages"""
        # Get session directory
        pstart = self.page(ui_pages.index("start.ui"))
        name = pstart.lineEdit_name.text()
        if pstart.radioButton_temp.isChecked():
            tdir = tempfile.mkdtemp(suffix=name, prefix="CellReel_")
            path = pathlib.Path(tdir)
        elif pstart.radioButton_home.isChecked():
            sesdir = time.strftime("%Y-%m-%d_%H:%M:%S")
            if name:
                sesdir += "_" + name
            path = pathlib.Path.home() / "CellReel" / sesdir
        elif pstart.radioButton_manual.isChecked():
            raise NotImplementedError("For now.")
        path.mkdir(parents=True, exist_ok=True)

        # Determine which task to perform
        pchoose = self.page(ui_pages.index("choose_data.ui"))
        if pchoose.radioButton_artificial.isChecked():
            # artificial data
            part = self.page(ui_pages.index("art_data.ui"))
            # assemble angles array
            ang_cov = np.deg2rad(part.spinBox_angcov.value())
            ang_num = part.spinBox_angnum.value()
            angles = np.linspace(0, ang_cov, ang_num, endpoint=False)
            # add angular skew
            ang_skew = np.deg2rad(part.spinBox_rot_skew.value())
            skt = np.linspace(0, 1, ang_num)
            angles += ang_skew * np.sin(2*np.pi * skt)

            task_simulate.simulate(
                path=path,
                phantom=part.comboBox_phantom.currentText(),
                angles=angles,
                duration=part.doubleSpinBox_duration.value(),
                displacement=part.doubleSpinBox_disp.value(),
                axis_roll=np.deg2rad(part.doubleSpinBox_axis_roll.value()),
                fluorescence=part.checkBox_fl.isChecked(),
                fl_frame_rate_mult=part.doubleSpinBox_fl_fr_mult.value(),
                fl_offsets=(part.doubleSpinBox_fl_start.value(),
                            part.doubleSpinBox_fl_end.value()),
                fl_bleach_decay=part.doubleSpinBox_fl_bleach.value(),
                fl_background=part.doubleSpinBox_flbg.value(),
            )
        elif (pchoose.radioButton_own_data.isChecked()
                or pchoose.radioButton_download.isChecked()):
            # user data
            pown = self.page(ui_pages.index("own_data.ui"))
            pownbg = self.page(ui_pages.index("own_data_bg.ui"))
            powncol = self.page(ui_pages.index("own_data_coloc.ui"))
            # roi data
            py, px = pownbg.roi.pos()
            sy, sx = pownbg.roi.size()
            # background correction data
            bgkw_qpi = {}
            for kk in dict(pownbg.params.getValues()).keys():
                bgkw_qpi[kk] = pownbg.params.child(kk).value()
            start = pownbg.spinBox_start.value()
            end = pownbg.spinBox_end.value()
            # store data hints
            hints = {"path_fl": pown.path_data_fl,
                     "path_qpi_bg": pown.path_data_qpi_bg,
                     "path_reference_qpi": powncol.path_data_qp,
                     "path_reference_fli": powncol.path_data_fl,
                     "wavelength": pown.params_meta_qp["wavelength"],
                     "pixel size": pown.params_meta_qp["pixel size"],
                     "medium index": pown.params_meta_qp["medium index"],
                     "pixel size fl": pown.params_meta_fl["pixel size"],
                     "roi pos": (py, px),
                     "roi size": (sy, sx),
                     "background correction": bgkw_qpi,
                     "coloc qp": self.get_coloc_kwargs()["p_qp"],
                     "coloc fl": self.get_coloc_kwargs()["p_fl"],
                     "interval start": start,
                     "interval end": end,
                     }
            meta_hints.save_hints(path_qpi=pown.path_data_qpi, hints=hints)
            # perform conversion
            task_convert.convert(
                path_out=path,
                path_qpi=pown.path_data_qpi,
                path_qpi_bg=pown.path_data_qpi_bg,
                path_fl=pown.path_data_fl,
                wavelength=pown.params_meta_qp["wavelength"]*1e-9,
                pixel_size=pown.params_meta_qp["pixel size"]*1e-6,
                medium_index=pown.params_meta_qp["medium index"],
                slice_qpi=(slice(int(px), int(px+sx)),
                           slice(int(py), int(py+sy))),
                interval_qpi=(start, end),
                bgkw_qpi=bgkw_qpi,
                colockw=self.get_coloc_kwargs(),
            )

        self.path = path

    def get_coloc_kwargs(self):
        pown = self.page(ui_pages.index("own_data.ui"))
        powncoloc = self.page(ui_pages.index("own_data_coloc.ui"))
        kw = {"p_qp": (powncoloc.p_qpx.value(), powncoloc.p_qpy.value()),
              "p_fl": (powncoloc.p_flx.value(), powncoloc.p_fly.value()),
              "res_qp": pown.params_meta_qp["pixel size"],
              "res_fl": pown.params_meta_fl["pixel size"],
              }
        return kw

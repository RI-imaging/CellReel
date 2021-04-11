import pkg_resources

from PyQt5 import uic, QtWidgets

from . import task_align


ui_pages = ["scheme.ui",
            "thresh.ui",
            ]


class AlignPage(QtWidgets.QWizardPage):
    """Alignment wizard page base"""

    def __init__(self, ui_name, *args, **kwargs):
        super(AlignPage, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename(
            "cellreel.wiz_align", ui_name)
        uic.loadUi(path_ui, self)
        self.ui_name = ui_name


class AlignPageScheme(AlignPage):
    """Alignment wizard page for selecting alignment method"""

    def initializePage(self):
        self.comboBox.clear()
        self.comboBox.addItems(sorted(task_align.ALIGN_METHODS.keys()))


class AlignPageThresh(AlignPage):
    """Alignment wizard page for selecting/visualizing thresholds"""

    def __init__(self, *args, **kwargs):
        super(AlignPageThresh, self).__init__(*args, **kwargs)
        # defaults
        self.ImageView.ui.histogram.hide()
        self.ImageView.ui.roiBtn.hide()
        self.ImageView.ui.menuBtn.hide()
        # set possible thresholds
        # TODO (from scikit-image)
        # connect slider event
        self.horizontalSlider.valueChanged.connect(self.on_slider)
        # connect manual spinbox
        self.doubleSpinBox.valueChanged.connect(self.on_slider)

    def get_threshold_kw(self):
        """Return the currently selected threshold"""
        method = self.comboBox.currentText()
        kw = {}
        if method == "Manual":
            kw["thresh"] = self.doubleSpinBox.value()
        else:
            raise NotImplementedError("Unknown threshold: {}".format(method))
        return kw

    def initializePage(self):
        """Setup data visualization"""
        wiz = self.wizard()
        pscheme = wiz.page(ui_pages.index("scheme.ui"))
        if pscheme.radioButton_pha.isChecked():
            self.data_name = "phase"
        elif pscheme.radioButton_amp.isChecked():
            self.data_name = "amplitude"
        else:
            self.data_name = "fluorescence"
        self.horizontalSlider.setMinimum(0)
        data = wiz.data.get_data(self.data_name)
        self.horizontalSlider.setMaximum(data.shape[0]-1)
        self.horizontalSlider.setValue(0)
        self.on_slider()

    def on_slider(self):
        """Display the threshold image selected by self.horizontalSlider"""
        idx = self.horizontalSlider.value()
        wiz = self.wizard()
        data = wiz.data.get_data(self.data_name)
        image = data[idx]
        kw = self.get_threshold_kw()
        self.ImageView.setImage(task_align.threshold(image, **kw))


class AlignWizard(QtWidgets.QWizard):
    """Data alignment wizard"""

    def __init__(self, name, data, path_out):
        super(AlignWizard, self).__init__(None)
        self._init_pages()
        self.setWindowTitle("CellReel sinogram alignment")
        self.resize(640, 480)

        self.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self._finalize)

        self.name = name
        self.data = data
        self.path_out = path_out

    def _init_pages(self):
        """Initializes all pages with their dedicated logic"""
        for pp in ui_pages:
            if pp == "thresh.ui":
                page = AlignPageThresh(pp, self)
            elif pp == "scheme.ui":
                page = AlignPageScheme(pp, self)
            else:
                page = AlignPage(pp, self)
            self.addPage(page)

    def _finalize(self):
        """Trigger alignment task with data from wizard pages"""
        # Get sinogram
        pscheme = self.page(ui_pages.index("scheme.ui"))
        pthresh = self.page(ui_pages.index("thresh.ui"))
        task_align.align(
            method=pscheme.comboBox.currentText(),
            mode=pthresh.data_name,
            preproc_kw=pthresh.get_threshold_kw(),
            data=self.data,
            name=self.name,
            path_out=self.path_out)

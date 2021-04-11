import pkg_resources

from PyQt5 import uic, QtWidgets

from . import task_bleach


ui_pages = ["bleach.ui",
            ]


class FluorescencePage(QtWidgets.QWizardPage):
    """Fluorescence wizard page base"""

    def __init__(self, ui_name, *args, **kwargs):
        super(FluorescencePage, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename(
            "cellreel.wiz_flcorr", ui_name)
        uic.loadUi(path_ui, self)
        self.ui_name = ui_name


class FluorescenceWizard(QtWidgets.QWizard):
    """Fluorescence correction wizard"""

    def __init__(self, name, data, path_out):
        super(FluorescenceWizard, self).__init__(None)
        self._init_pages()
        self.setWindowTitle("CellReel fluorescence correction")
        self.resize(640, 480)

        self.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self._finalize)

        self.name = name
        self.data = data
        self.path_out = path_out

    def _init_pages(self):
        """Initialize all wizard pages"""
        for pp in ui_pages:
            page = FluorescencePage(pp, self)
            self.addPage(page)

    def _finalize(self):
        """Trigger fluorescence correction task with data from wizard pages"""
        pbleach = self.page(ui_pages.index("bleach.ui"))
        task_bleach.bleach_correction(
            denoise=pbleach.checkBox_denoise.isChecked(),
            border_px=pbleach.spinBox_border.value(),
            data=self.data,
            name=self.name,
            path_out=self.path_out)

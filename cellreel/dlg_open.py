import pathlib
import pkg_resources

from PyQt5 import uic, QtWidgets


class OpenDialog(QtWidgets.QDialog):
    """A dialog for opening CellReel sessions"""

    def __init__(self, *args, **kwargs):
        super(OpenDialog, self).__init__(*args, **kwargs)
        path_ui = pkg_resources.resource_filename("cellreel", "dlg_open.ui")
        uic.loadUi(path_ui, self)

        # initialize
        self.paths = self._get_standard_paths()
        self.listWidget_paths.addItems([str(p) for p in self.paths])
        self.listWidget_paths.setCurrentRow(len(self.paths)-1)
        self.listWidget_paths.setFocus()
        self._path = None

    def _get_standard_paths(self):
        """Return list of paths in users home / CellReel directory"""
        path = pathlib.Path.home() / "CellReel"
        paths = [p for p in path.glob("*") if p.is_dir()]
        return sorted(paths)

    def get_path(self):
        """Return path corresponding to currently selected list element"""
        if self._path is None:
            if self.paths:
                # path from listWidget
                idx = self.listWidget_paths.currentRow()
                path = self.paths[idx]
            else:
                path = None
        else:
            # manual path
            path = self._path
        return path

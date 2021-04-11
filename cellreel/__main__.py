import sys

from PyQt5 import QtWidgets

from .main import CellReelMain


if __name__ == '__main__':
    # Start App
    app = QtWidgets.QApplication(sys.argv)
    mainw = CellReelMain()
    mainw.show()
    sys.exit(app.exec_())

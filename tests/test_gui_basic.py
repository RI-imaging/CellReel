"""basic tests"""
from cellreel.main import CellReelMain


def test_simple(qtbot):
    """Open the main window and close it again"""
    main_window = CellReelMain()
    main_window.close()

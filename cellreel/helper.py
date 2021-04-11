import matplotlib.cm as cm
import numpy as np
import pyqtgraph as pg


def get_cmap(name):
    """Get matplotlib colormap as PyQtGraph ColorMap"""
    m = cm.get_cmap(name)
    points = np.linspace(0, 1, 100, endpoint=True)
    color = np.array([m(p) for p in points])*255
    return pg.ColorMap(pos=points, color=color)

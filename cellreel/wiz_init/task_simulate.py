import multiprocessing as mp
import time

import cellsino
import numpy as np
from PyQt5 import QtCore, QtWidgets


class SinoThread(QtCore.QThread):
    def __init__(self, sino, qpskw, flskw, *args, **kwargs):
        super(SinoThread, self).__init__(*args, **kwargs)
        self.sino = sino
        self.qpskw = qpskw
        self.flskw = flskw

    def run(self):
        self.sino.compute(**self.qpskw)
        if self.flskw:
            self.sino.compute(**self.flskw)


def simulate(path, phantom, angles, duration=3, displacement=0, axis_roll=0,
             fluorescence=True, fl_frame_rate_mult=1, fl_offsets=(0, 0),
             fl_bleach_decay=0, fl_background=0, wavelength=550e-9,
             pixel_size=0.08e-6, grid_size=(250, 250)):
    """Simulate a fluorescence and refractive index tomography

    Uses :mod:`cellsino` for computing the actual sinograms.

    Parameters
    ----------
    path: pathlib.Path
        Path where the output data are be stored.
    phantom: str
        Name of the cell phantom to use. See
        :data:`cellsino.phantoms.available` for valid options.
    angles: 1d ndarray
        Sinogram recording angles [rad]
    duration: float
        Measurement duration [s]
    displacement: float
        Standard deviation of the lateral displacement noise
    axis_roll: float
        Lateral (in-plane) rotation of the rotational axis.
    fluorescence: bool
        If set to False, no fluorescence sinogram is generated.
    fl_frame_rate_mult: float
        Fluorescence frame rate multiplier. Set this to a value
        other than "1" to modify the frame rate of the fluorescence
        sinogram data (w.r.t. the phase/amplitude sinogram). Values
        larger than "1" mean that the fluorescence sinogram data
        are recorded at higher frame rates.
    fl_offsets: tuple of float
        Fluorescence sinogram acquisition offsets define starting
        and stopping offsets for fluorescence sinogram acquisition.
        Negative values mean that the fluorescence sinogram
        acquisition started (stopped) earlier.
    fl_bleach_decay: float
        Photobleaching decay constant [1/s]
    fl_background: float
        Overall fluorescence background signal
    wavelength: float
        Imaging wavelength [m]
    pixel_size: float
        Detector pixel size [m]
    grid_size: tuple of int
        Output grid size [px]
    """
    sino = cellsino.Sinogram(phantom=phantom,
                             wavelength=wavelength,
                             pixel_size=pixel_size,
                             grid_size=grid_size)

    count = mp.Value('I', 0, lock=True)
    max_count = mp.Value('I', angles.size, lock=True)

    # In CellReel, we have a slightly different definition of the
    # default rotation axis:
    qpskw = {"angles": -angles,
             "axis_roll": -axis_roll + np.pi/2,
             "displacements": displacement,
             "times": duration,
             "mode": "field",
             "path": path / "sinogram.h5",
             "count": count,
             }

    if fluorescence:
        # compute times for fluorescence sinogram images
        fl_time_start = fl_offsets[0]
        fl_time_end = fl_offsets[1] + duration
        fl_time_step = duration / angles.size / fl_frame_rate_mult
        fl_num = np.round((fl_time_end - fl_time_start) / fl_time_step)
        fl_times = np.linspace(fl_time_start, fl_time_end, int(fl_num),
                               endpoint=False)
        # compute angles for fluorescence sinogram images
        angle_step = angles[1] - angles[0]
        ang_max = angles[-1] + angle_step  # last element not in array
        fl_angles = fl_times / duration * ang_max
        flskw = {"angles": -fl_angles,
                 "axis_roll": -axis_roll + np.pi/2,
                 "displacements": displacement,
                 "times": fl_times,
                 "mode": "fluorescence",
                 "bleach_decay": fl_bleach_decay,
                 "fluorescence_background": fl_background,
                 "path": path / "sinogram.h5",
                 "count": count,
                 }
        # increment max progress bar
        max_count.value += fl_angles.size
    else:
        flskw = {}

    bar = QtWidgets.QProgressDialog("Generating sinogram data...",
                                    "This button does nothing",
                                    count.value,
                                    max_count.value)
    bar.setCancelButton(None)
    bar.setMinimumDuration(0)
    bar.setAutoClose(True)
    bar.setWindowTitle("Simulation")

    sinothread = SinoThread(sino=sino, qpskw=qpskw, flskw=flskw)
    sinothread.start()

    # Show a progress until computation is done
    while count.value == 0 or count.value < max_count.value:
        time.sleep(.05)
        bar.setValue(count.value)
        bar.setMaximum(max_count.value)
        QtCore.QCoreApplication.instance().processEvents()

    # make sure the thread finishes
    sinothread.wait()

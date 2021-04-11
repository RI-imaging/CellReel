import multiprocessing as mp
import os
import tempfile
import time

import flimage
import h5py
import numpy as np
from PyQt5 import QtCore, QtWidgets

from .._version import version


class BGThread(QtCore.QThread):
    def __init__(self, func, fkw, *args, **kwargs):
        super(BGThread, self).__init__(*args, **kwargs)
        self.func = func
        self.fkw = fkw

    def run(self):
        self.result = self.func(**self.fkw)


def bleach_correction(denoise, border_px, data, name, path_out):
    """Perform bleach correction

    Parameters
    ----------
    denoise: bool
        Whether to perform the fluorescence correction for the
        denoised image. This is highly recommended.
    border_px: int
        Number of pixels to use from the border of the image for
        background fluorescence signal correction.
    data: cellreel.sino.sino_view.SinoView
        Full sinogram data
    name: str
        Name of the new sinogram
    path_out: pathlib.Path
        Output sinogram HDF5 file

    Notes
    -----
    The fluorescence sinogram is also background corrected
    (background offset signal).
    """
    count = mp.Value('I', 0, lock=True)
    max_count = mp.Value('I', 0, lock=True)

    bar = QtWidgets.QProgressDialog("Preprocessing data...",
                                    "This button does nothing",
                                    count.value,
                                    max_count.value)
    bar.setCancelButton(None)
    bar.setAutoClose(False)
    bar.setMinimumDuration(0)
    bar.setWindowTitle("Bleach correction")

    # temporary path for all operations
    path_temp = tempfile.mktemp(suffix=".h5",
                                prefix=".bleach",
                                dir=path_out.parent)

    with h5py.File(data.path, "r") as h5in, \
        h5py.File(path_temp, "w") as h5temp, \
            h5py.File(path_out, "w") as h5out:
        flsin = flimage.FLSeries(h5file=h5in["flseries"])
        # denoise
        dnkw = {"h5file": h5temp.require_group("flseries"),
                "count": count,
                "max_count": max_count,
                }
        denthread = BGThread(func=flsin.denoise, fkw=dnkw)
        denthread.start()
        # Show a progress until computation is done
        while count.value == 0 or count.value < max_count.value:
            time.sleep(.05)
            bar.setValue(count.value)
            bar.setMaximum(max_count.value)
            QtCore.QCoreApplication.instance().processEvents()
        # make sure the thread finishes
        denthread.wait()

        # bleach correction
        count.value = 0
        max_count.value = 0
        bar.setLabelText("Performing bleach correction...")
        bar.setValue(0)
        bar.setAutoClose(True)
        flstemp = flimage.FLSeries(h5file=h5temp["flseries"])
        if denoise:
            flscorr = flstemp
        else:
            flscorr = flsin
        bckw = {"flscorr": flscorr,
                "h5out": h5out.require_group("flseries"),
                "border_px": border_px,
                "count": count,
                "max_count": max_count,
                }
        blthread = BGThread(func=flsin.bleach_correction, fkw=bckw)
        blthread.start()
        # Show a progress until computation is done
        while count.value == 0 or count.value < max_count.value:
            time.sleep(.05)
            bar.setValue(count.value)
            bar.setMaximum(max_count.value)
            QtCore.QCoreApplication.instance().processEvents()
        # make sure the thread finishes
        blthread.wait()
        # write bleach correction data
        bg, flint, decay, times = blthread.result
        bdata = np.zeros(times.size, np.dtype([("time", np.float),
                                               ("signal", np.float),
                                               ("fit", np.float)]))
        bdata["time"] = times
        bdata["signal"] = flint
        bdata["fit"] = decay
        blc = h5out.create_group("bleach correction")
        blc.attrs["background signal"] = bg
        blcds = blc.create_dataset(name="fit", data=bdata)
        blcds.attrs["CLASS"] = np.string_("TABLE")
        blcds.attrs["TITLE"] = np.string_("Bleach correction")
        blcds.attrs["VERSION"] = np.string_("0.2")
        blcds.attrs["FIELD_0_NAME"] = np.string_("time")
        blcds.attrs["FIELD_1_NAME"] = np.string_("signal")
        blcds.attrs["FIELD_2_NAME"] = np.string_("fit")
        # set meta data
        h5out.attrs["bleach correction border_px"] = border_px
        h5out.attrs["bleach correction denoise"] = denoise
        h5out.attrs["CellReel version"] = version
        h5out.attrs["name"] = name
        h5out.attrs["origin hash"] = data.get_hash()
        # copy qpi data
        h5in.copy("qpseries", h5out)

    # cleanup
    os.remove(path_temp)

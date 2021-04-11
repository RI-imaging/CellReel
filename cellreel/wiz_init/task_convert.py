import multiprocessing as mp
import time

import flimage
import h5py
from PyQt5 import QtCore, QtWidgets
import qpformat
import qpimage


from . import coloc
from .formats import flformat
from .._version import version


class ConvertThread(QtCore.QThread):
    def __init__(self, ds, dskw, *args, **kwargs):
        super(ConvertThread, self).__init__(*args, **kwargs)
        self.ds = ds
        self.dskw = dskw

    def run(self):
        self.ds.saveh5(**self.dskw)


def convert(path_out, path_qpi, path_qpi_bg, path_fl, wavelength, pixel_size,
            medium_index, slice_qpi, interval_qpi, bgkw_qpi, colockw):
    """Convert experimental data to the subjoined QPSeries/FLSeries format

    Parameters
    ----------
    path_out: pathlib.Path
        Output HDF5 file
    path_qpi: pathlib.Path
        Path to quantitative phase data
    path_qpi: pathlib.Path
        Path to quantitative phase background data
    path_fl: pathlib.Path
        Path to fluorescence data
    wavelength: float
        QPI imaging wavelength [m]
    pixel_size: float
        QPI pixel size
    medium_index:
        Sample medium index
    slice_qpi: slice
        Slice region of interest of the original data to be imported;
        ``(slice(0, -1), slice(0, -1))`` corresponds to the whole
        sensor image.
    interval_qpi: tuple of ints
        Data interval to use (last frame included)
    bgkw_qpi: dict
        Additional background keyword arguments
        (see :class:`qpimage.QPImage`)
    """
    count = mp.Value('I', 0, lock=True)
    max_count = mp.Value('I', 0, lock=True)

    ds_qp = qpformat.load_data(path=path_qpi,
                               bg_data=path_qpi_bg,
                               meta_data={"wavelength": wavelength,
                                          "pixel size": pixel_size,
                                          "medium index": medium_index})

    ta = ds_qp.get_time(interval_qpi[0])
    tb = ds_qp.get_time(interval_qpi[1])

    if path_fl:
        ds_fl = flformat.load_data(path=path_fl)
        ta = max(ta, ds_fl.get_time(0))
        tb = min(tb, ds_fl.get_time(len(ds_fl) - 1))

    path_sino = path_out / "sinogram.h5"

    with h5py.File(path_sino, mode="w") as h5:
        h5.attrs["CellReel version"] = version
        h5qps = h5.require_group("qpseries")
        dskw = {"count": count,
                "max_count": max_count,
                "h5file": h5qps,
                "qpi_slice": slice_qpi,
                "time_interval": (ta, tb),
                }
        convthread = ConvertThread(ds=ds_qp, dskw=dskw)
        convthread.start()

        bar = QtWidgets.QProgressDialog("Converting QPI data...",
                                        "This button does nothing",
                                        count.value,
                                        max_count.value)
        bar.setCancelButton(None)
        bar.setAutoClose(False)
        bar.setMinimumDuration(0)
        bar.setWindowTitle("Measurement import")

        # Show a progress until computation is done
        while count.value == 0 or count.value < max_count.value:
            time.sleep(.05)
            bar.setValue(count.value)
            bar.setMaximum(max_count.value)
            QtCore.QCoreApplication.instance().processEvents()

        # make sure the thread finishes
        convthread.wait()

        # Perform background correction
        with qpimage.QPSeries(h5file=h5qps) as qps:
            bar.setLabelText("Performing QPI background correction...")
            bar.setValue(0)
            bar.setMaximum(len(qps))
            if path_fl is None:
                bar.setAutoClose(True)

            for qpi in qps:
                # initial time
                qpi["time"] = qpi["time"] - ta
                # background correction
                qpi.compute_bg(which_data=["phase", "amplitude"], **bgkw_qpi)
                bar.setValue(bar.value() + 1)
                QtCore.QCoreApplication.instance().processEvents()

        if path_fl:
            # load fluorescence data
            bar.setLabelText("Converting fluorescence data...")
            bar.setValue(0)
            bar.setMaximum(len(ds_fl))
            bar.setAutoClose(True)

            h5fls = h5.require_group("flseries")
            qpi_shape = ds_qp.get_qpimage(0).shape
            with flimage.FLSeries(h5file=h5fls) as fls:
                for ii in range(len(ds_fl)):
                    ti = ds_fl.get_time(ii)
                    if ti >= ta and ti <= tb:
                        # get original data
                        fli = ds_fl.get_flimage(ii)
                        # warp data to qps sensor image
                        flw = coloc.warp_fl(fl=fli.fl,
                                            output_shape=qpi_shape,
                                            **colockw)
                        # create new FLImage using given ROI
                        meta_data = fli.meta.copy()
                        meta_data["pixel size"] = pixel_size
                        meta_data["time"] = fli["time"] - ta
                        fln = flimage.FLImage(data=flw[slice_qpi],
                                              meta_data=meta_data
                                              )
                        fls.add_flimage(fln)

                    bar.setValue(bar.value() + 1)
                    QtCore.QCoreApplication.instance().processEvents()

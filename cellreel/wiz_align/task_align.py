import flimage
import h5py
import numpy as np
from PyQt5 import QtCore, QtWidgets
import qpimage
import scipy.ndimage.interpolation as intp
from skimage.segmentation import clear_border
from skimage.measure import regionprops
from skimage.morphology import closing, square


from .._version import version


def align(method, mode, preproc_kw, data, name, path_out):
    """Alignment sinogram data

    Parameters
    ----------
    method: str
        Alignment method key; See :data:`ALIGN_METHODS`
    mode: str
        Which imaging modality to use for singram alignment (phase,
        amplitude, or fluorescence)
    preproc_kw: dict
        Keyword arguments for preprocessing; Each alignment method
        has a preprocessing method associated with it.
    data: cellreel.sino.sino_view.SinoView
        Full sinogram data
    name: str
        Name of the aligned sinogram (stored in HDF5 file)
    path_out: str or pathlib.Path
        Path to output sinogram HDF5 file

    Notes
    -----
    Uses linear interpolation on time axis to correct shift
    for complementary imaging modality.
    """
    pfunc, mfunc = ALIGN_METHODS[method]

    with h5py.File(path_out, "w") as h5out:
        h5out.attrs["name"] = name
        h5out.attrs["CellReel version"] = version
        h5out.attrs["origin hash"] = data.get_hash()
        h5out.attrs["alignment method"] = method
        h5out.attrs["alignment modality"] = mode
        for key in preproc_kw:
            kk = "alignment preprocessing {}".format(key)
            h5out.attrs[kk] = preproc_kw[key]

        image_data = data.get_data(mode)

        lendat = 0
        if data.has_fli():
            lendat += data.fl.shape[0]
        if data.has_qpi():
            # counts twice
            lendat += 2*data.pha.shape[0]

        bar = QtWidgets.QProgressDialog("Transforming data...",
                                        "This button does nothing",
                                        0,
                                        lendat)
        bar.setCancelButton(None)
        bar.setMinimumDuration(0)
        bar.setAutoClose(True)
        bar.setWindowTitle("Sinogram Alignment")

        shiftx = np.zeros(len(image_data))
        shifty = np.zeros(len(image_data))

        for ii in range(len(image_data)):
            image = image_data[ii]
            # run pipeline
            preproc = pfunc(image, **preproc_kw)
            shift = mfunc(preproc)
            shiftx[ii] = shift[0]
            shifty[ii] = shift[1]

        times = data.get_times(mode=mode)

        skw = {"mode": "constant",
               "order": 3,
               }

        if data.has_qpi():
            qps_group = h5out.require_group("qpseries")
            times_qp = data.get_times("phase")
            shiftx_qp = np.interp(x=times_qp, xp=times, fp=shiftx)
            shifty_qp = np.interp(x=times_qp, xp=times, fp=shifty)
            with qpimage.QPSeries(h5file=qps_group) as qps:
                for ii in range(data.pha.shape[0]):
                    sh = (shiftx_qp[ii], shifty_qp[ii])
                    phai = intp.shift(
                        input=data.pha[ii], cval=0, shift=sh, **skw)
                    ampi = intp.shift(
                        input=data.amp[ii], cval=1, shift=sh, **skw)
                    qpio = qpimage.QPImage(data=(phai, ampi),
                                           which_data="phase,amplitude",
                                           meta_data=data.meta_qpi[ii])
                    qps.add_qpimage(qpi=qpio)
                    bar.setValue(bar.value() + 2)
                    QtCore.QCoreApplication.instance().processEvents()

        if data.has_fli():
            fls_group = h5out.require_group("flseries")
            times_fl = data.get_times("fluorescence")
            shiftx_fl = np.interp(x=times_fl, xp=times, fp=shiftx)
            shifty_fl = np.interp(x=times_fl, xp=times, fp=shifty)
            with flimage.FLSeries(h5file=fls_group) as fls:
                for ii in range(data.fl.shape[0]):
                    sh = (shiftx_fl[ii], shifty_fl[ii])
                    fli = intp.shift(
                        input=data.fl[ii], cval=0, shift=sh, **skw)
                    flio = flimage.FLImage(data=fli,
                                           meta_data=data.meta_fli[ii])
                    fls.add_flimage(fli=flio)
                    bar.setValue(bar.value() + 1)
                    QtCore.QCoreApplication.instance().processEvents()


def bbox(binary):
    proi = regionprops(binary)[0]
    min_row, min_col, max_row, max_col = proi.bbox
    center = np.array([(max_row+min_row)/2, (max_col+min_col)/2])
    shift = np.array(binary.shape)/2 - center
    return shift


def centroid(binary):
    """Return the x-y-shift necessary to center the binary image"""
    proi = regionprops(binary)[0]
    shift = np.array(binary.shape)/2 - proi.centroid
    return shift


def threshold(image, thresh):
    """Compute the threshold of an image"""
    if isinstance(thresh, float):
        pass
    else:
        raise NotImplementedError("Unknown threshold: {}".format(thresh))
    bw = closing(image > thresh, square(3))
    # remove artifacts connected to image border
    cleared = np.asarray(clear_border(bw), dtype=int)
    return cleared


#: Valid alignment methods
ALIGN_METHODS = {"Center of bounding box (threshold image)": (threshold, bbox),
                 "Center of mass (threshold image)": (threshold, centroid),
                 }

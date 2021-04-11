from functools import lru_cache
import hashlib
import numbers

import flimage
import h5py
import numpy as np
from pyqtgraph.functions import affineSlice
import qpimage


class SinoView(object):
    def __init__(self, path=None):
        self.path = path

    def convert_index_to_time(self, idx, mode):
        assert mode in ["phase", "amplitude", "fluorescence"]
        if not isinstance(idx, numbers.Number):
            # iterate
            out = []
            for ix in idx:
                out.append(self.convert_index_to_time(ix, mode))
        else:
            t0 = self.get_times(mode=mode)[0]
            frame_rate = self.get_frame_rate(mode=mode)
            out = t0 + idx / frame_rate
        return out

    def convert_time_to_index(self, time, mode, integer=False):
        assert mode in ["phase", "amplitude", "fluorescence"]
        if not isinstance(time, numbers.Number):
            # iterate
            out = []
            for ti in time:
                out.append(self.convert_time_to_index(ti, mode, integer))
        else:
            t0 = self.get_times(mode=mode)[0]
            frame_rate = self.get_frame_rate(mode=mode)
            out = (time - t0) * frame_rate
            if integer:
                out = int(np.round(out))
        return out

    def get_data(self, mode="phase"):
        """Return the sinogram data corresponding to `mode`"""
        if mode not in ["phase", "amplitude", "fluorescence"]:
            raise ValueError("Invalid modality: {}".format(mode))
        if mode == "phase":
            return self.pha
        elif mode == "amplitude":
            return self.amp
        else:
            return self.fl

    @lru_cache(maxsize=None)
    def get_frame_rate(self, mode="phase", ret_var=False):
        """Compute the mean recording frame rate for the image modality

        Parameters
        mode: str
            Imaging modality ("phase", "amplitude", or "fluorescence")
        ret_var: bool
            Return the frame rate variance [%]
        """
        times = self.get_times(mode=mode)
        tdiff = np.diff(times)
        tdiff = tdiff[tdiff != 0]  # ignore frames with zero difference
        rates = 1 / tdiff
        frame_rate = np.mean(rates)
        variance = np.var(rates) / frame_rate * 100
        if ret_var:
            return frame_rate, variance
        else:
            return frame_rate

    @lru_cache(maxsize=None)
    def get_hash(self):
        """Return the hash of the current sinogram HDF5 file"""
        hasher = hashlib.md5()
        bs = 65536
        with self.path.open("rb") as fd:
            buf = fd.read(bs)
            while len(buf) > 0:
                hasher.update(buf)
                buf = fd.read(bs)
        return hasher.hexdigest()

    @lru_cache(maxsize=None)
    def get_meta(self, mode="phase"):
        assert mode in ["phase", "amplitude", "fluorescence"]
        with h5py.File(self.path, mode="r") as h5:
            if mode == "fluorescence":
                ser = flimage.FLSeries(h5file=h5["flseries"], h5mode="r")
            else:
                ser = qpimage.QPSeries(h5file=h5["qpseries"], h5mode="r")
            meta = ser[0].meta
        return meta

    @lru_cache(maxsize=None)
    def get_size(self, mode="phase"):
        assert mode in ["phase", "amplitude", "fluorescence"]
        with h5py.File(self.path, mode="r") as h5:
            if mode == "fluorescence":
                size = len(h5["flseries"])
            else:
                size = len(h5["qpseries"])
        return size

    def get_slice(self, position, angle, data, offset=0, fillval=0):
        """Get slice by interpolation"""
        angle = np.deg2rad(angle)
        v1 = [1, 0, 0]
        v2 = [0, np.cos(angle), np.sin(angle)]
        # origin
        center = (np.array(data.shape[1:])-1) / 2
        R = np.array([[np.cos(angle), -np.sin(angle)],
                      [np.sin(angle), np.cos(angle)]])
        Ri = np.linalg.inv(R)
        Pb1 = np.array(position)[::-1] - center  # center
        Pbb1 = np.dot(Ri, Pb1)  # rotate
        # take x coord and set origin
        Pbb2 = np.array([-center[0], Pbb1[1]+offset])
        Pb2 = np.dot(R, Pbb2)  # rotate back
        position2 = Pb2 + center  # set center

        origin = np.array([0, position2[0], position2[1]])
        shape = (data.shape[0], data.shape[1])
        image = affineSlice(data=data,
                            shape=shape,
                            origin=origin,
                            vectors=[v1, v2],
                            axes=(0, 1, 2),
                            )
        if fillval:  # workaround
            image[image == 0] = fillval
        return image

    @lru_cache(maxsize=None)
    def get_times(self, mode="phase"):
        """Get the recording times for each image of an imaging modality
        """
        if mode not in ["phase", "amplitude", "fluorescence"]:
            raise ValueError("Invalid modality: {}".format(mode))
        if mode in ["phase", "amplitude"]:
            if not self.has_qpi():
                raise ValueError("No QPI data available, cannot get "
                                 "frame rate for `{}`!".format(mode))
            with h5py.File(self.path, mode="r") as h5:
                qps = qpimage.QPSeries(h5file=h5["qpseries"])
                times = [qpi["time"] for qpi in qps]
        else:
            if not self.has_fli():
                raise ValueError("No Fluorescence data available, cannot get "
                                 "frame rate for `{}`!".format(mode))
            with h5py.File(self.path, mode="r") as h5:
                fls = flimage.FLSeries(h5file=h5["flseries"])
                times = [fli["time"] for fli in fls]
        return np.array(times)

    def get_time_slice(self, t_start, t_end, mode):
        times = self.get_times(mode=mode)
        start = np.sum(times < t_start)
        end = times.size - np.sum(times > t_end)
        angle_slice = slice(start, end)
        return angle_slice

    @lru_cache(maxsize=None)
    def has_fli(self):
        """Whether the current sinogram contains fluorescence data"""
        with h5py.File(self.path, "r") as h5:
            return "flseries" in h5

    @lru_cache(maxsize=None)
    def has_qpi(self):
        """Whether the current sinogram contains quantitative phase data"""
        with h5py.File(self.path, "r") as h5:
            return "qpseries" in h5

    def is_aligned(self):
        pass

    def is_colocalized(self):
        pass

    def load(self, count=None, max_count=None):
        """Load sinogram data into memory"""
        # set maximum count value for progress tracking
        if max_count is not None:
            with h5py.File(self.path, "r") as h5:
                if self.has_qpi():
                    max_count.value += 2*len(h5["qpseries"].keys())
                if self.has_fli():
                    max_count.value += len(h5["flseries"].keys())
        self.meta = {}
        self.meta_qpi = []
        self.meta_fli = []
        with h5py.File(self.path, mode="r") as h5:
            if self.has_qpi():
                qps = qpimage.QPSeries(h5file=h5["qpseries"])
                qp0 = qps[0]
                for key in ["wavelength", "pixel size", "medium index"]:
                    self.meta[key] = qp0[key]
                sa = len(qps)
                sx, sy = qp0.shape
                dtype = qp0.dtype
                self.amp = np.zeros((sa, sx, sy), dtype=dtype)
                self.pha = np.zeros((sa, sx, sy), dtype=dtype)
                for ii in range(sa):
                    self.meta_qpi.append(qps[ii].meta)
                    self.pha[ii] = qps[ii].pha
                    self.amp[ii] = qps[ii].amp
                    if count is not None:
                        count.value += 2
            else:
                self.amp = None
                self.pha = None
            if self.has_fli():
                fls = flimage.FLSeries(h5file=h5["flseries"])
                fl0 = fls[0]
                fsa = len(fls)
                fsx, fsy = fl0.shape
                dtype = fl0.dtype
                self.fl = np.zeros((fsa, fsx, fsy), dtype=dtype)
                for jj in range(fsa):
                    self.meta_fli.append(fls[jj].meta)
                    self.fl[jj] = fls[jj].fl
                    if count is not None:
                        count.value += 1
            else:
                self.fl = None
        # clear lru_caches
        for key in dir(self):
            obj = getattr(self, key)
            if callable(obj) and hasattr(obj, "cache_clear"):
                obj.cache_clear()
        return self

    def verify(self, nest=True):
        """Verify the analysis steps leading to this sinogram

        Use reference path and other options in self.h5.attrs
        to reproduce this very sinogram.

        Paramters
        ---------
        nest: bool
            Perform the same for any sinogram which the
            current sinogram is derived from.
        """
        pass

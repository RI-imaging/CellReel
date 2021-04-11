import pathlib
import sys
import warnings

import flimage
import h5py
import imageio
import numpy as np
import tifffile

from .dataset import DataSet


ISWIN = sys.platform.startswith("win")


class SeriesAvi(DataSet):
    def __init__(self, *args, **kwargs):
        super(SeriesAvi, self).__init__(*args, **kwargs)
        self._cap = None
        self._length = None
        self._frame_times = None

    def __del__(self):
        if self._cap is not None:
            if ISWIN:
                # This is a workaround for windows when pytest fails due
                # to "OSError: [WinError 6] The handle is invalid",
                # which is somehow related to the fact that "_proc.kill()"
                # must be called twice (in "close()" and in this case) in
                # order to terminate the process and due to the fact the
                # we are not using the with-statement in combination
                # with imageio.get_reader().
                self._cap._proc.kill()
            self._cap.close()

    def __len__(self):
        """Returns the length of the video or `True` if the length cannot be
        determined.
        """
        if self._length is None:
            cap = self.video_handle
            length = len(cap)
            self._length = length
        return self._length

    def _get_frame(self, idx):
        """Returns the requested frame from the video in gray scale"""
        cap = self.video_handle
        cellimg = cap.get_data(idx)[::-1, :]
        if np.all(cellimg == 0):
            cellimg = self._get_image_workaround_seek(idx)
        # Convert to grayscale
        if len(cellimg.shape) == 3:
            cellimg = np.array(cellimg[:, :, 0])
        return cellimg

    def _get_image_workaround_seek(self, idx):
        """Same as __getitem__ but seek through the video beforehand
        This is a workaround for an all-zero image returned by `imageio`.
        """
        warnings.warn("imageio workaround used!")
        cap = self.video_handle
        mult = 50
        for ii in range(idx//mult):
            cap.get_data(ii*mult)
        final = cap.get_data(idx)[::-1, :]
        return final

    @property
    def frame_times(self):
        if self._frame_times is None:
            timfile = self.path.with_name(self.path.stem + "frametiming.txt")
            with timfile.open() as fd:
                data = fd.readlines()
            data = [d.strip() for d in data if len(d.strip()) != 0]
            times = [float(d[:2])*60*60+float(d[2:4])*60+float(d[4:])
                     for d in data]
            self._frame_times = times
            assert len(times) == len(self)
        return self._frame_times

    @property
    def video_handle(self):
        if self._cap is None:
            self._cap = imageio.get_reader(self.path)
        return self._cap

    def get_flimage(self, idx=0):
        fl = self._get_frame(idx)
        fli = flimage.FLImage(data=fl, meta_data=self.meta_data)
        fli["time"] = self.get_time(idx)
        fli["identifier"] = self.get_identifier(idx)
        return fli

    def get_time(self, idx):
        return self.frame_times[idx]


class SeriesH5(DataSet):
    def __init__(self, *args, **kwargs):
        super(SeriesH5, self).__init__(*args, **kwargs)
        self._init_meta()

    def __len__(self):
        with self._flseries() as fls:
            return len(fls)

    def _flseries(self):
        return flimage.FLSeries(h5file=self.path, h5mode="r")

    def _init_meta(self):
        # update meta data
        with h5py.File(self.path, mode="r") as h5:
            attrs = dict(h5["fli_0"].attrs)
        for key in flimage.meta.DATA_KEYS_FL:
            if (key not in self.meta_data
                    and key not in ["time"]  # do not override time
                    and key in attrs):
                self.meta_data[key] = attrs[key]

    def get_flimage(self, idx=0):
        with self._flseries() as fls:
            fli = fls[idx].copy()
        return fli

    def get_time(self, idx):
        with self._flseries() as fls:
            time = fls[idx].meta["time"]
        return time


class SingleH5(DataSet):
    def __init__(self, *args, **kwargs):
        super(SingleH5, self).__init__(*args, **kwargs)
        # update meta data
        with h5py.File(self.path, mode="r") as h5:
            attrs = dict(h5.attrs)
        for key in flimage.meta.DATA_KEYS_FL:
            if (key not in self.meta_data
                    and key in attrs):
                self.meta_data[key] = attrs[key]

    def get_flimage(self, idx=0):
        """Return background-corrected QPImage"""
        # We can use the background data stored in the qpimage hdf5 file
        fli = flimage.FLImage(h5file=self.path,
                              h5mode="r",
                              ).copy()
        # Force meta data
        for key in self.meta_data:
            fli[key] = self.meta_data[key]
        # set identifier
        fli["identifier"] = self.get_identifier(idx)
        return fli


class SingleTif(DataSet):
    def __len__(self):
        return 1

    def get_flimage(self, idx=0):
        if self.path.suffix == ".tif":
            fl = tifffile.imread(str(self.path))[::-1, :]
        fli = flimage.FLImage(data=fl, meta_data=self.meta_data)
        fli["identifier"] = self.get_identifier(idx)
        return fli


def load_data(path, meta_data={}):
    path = pathlib.Path(path)
    if path.suffix == ".tif":
        return SingleTif(path, meta_data=meta_data)
    elif path.suffix == ".avi":
        return SeriesAvi(path, meta_data=meta_data)
    elif path.suffix == ".h5":
        try:
            return SeriesH5(path, meta_data=meta_data)
        except KeyError:
            return SingleH5(path, meta_data=meta_data)

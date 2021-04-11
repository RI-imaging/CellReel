import copy
import functools
import hashlib
import io
import pathlib

import flimage
import numpy as np


class DataSet(object):
    def __init__(self, path, meta_data={}):
        """Fluorescence dataset base class"""
        #: Enforced dtype via keyword arguments
        if isinstance(path, io.IOBase):
            # io.IOBase
            self.path = path
        else:
            #: pathlib.Path to data file or io.IOBase
            self.path = pathlib.Path(path).resolve()

        # check for valid metadata keys
        for key in meta_data:
            if key not in flimage.meta.META_KEYS_FL:
                msg = "Invalid metadata key `{}`!".format(key) \
                      + "Valid keys: {}".format(flimage.meta.META_KEYS_FL)
                raise ValueError(msg)
        #: Enforced metadata via keyword arguments
        self.meta_data = copy.copy(meta_data)

    @functools.lru_cache(maxsize=32)
    def _copmute_identifier(self):
        data = []
        # data
        if isinstance(self.path, io.IOBase):
            self.path.seek(0)
            data.append(self.path.read(50 * 1024))
        else:
            with self.path.open("rb") as fd:
                data.append(fd.read(50 * 1024))
        # meta data
        for key in sorted(list(self.meta_data.keys())):
            value = self.meta_data[key]
            data.append("{}={}".format(key, value))
        return hash_obj(data)

    @property
    def identifier(self):
        """Return a unique identifier for the given data set"""
        return self._copmute_identifier()

    def get_identifier(self, idx):
        """Return an identifier for the data at index `idx`
        """
        return "{}:{}".format(self.identifier, idx + 1)

    def saveh5(self, h5file):
        """Save the data set as an hdf5 file (flimage.FLSeries format)

        Parameters
        ----------
        h5file: str, pathlib.Path, or h5py.Group
            Where to store the series data
        """

        qpskw = {"h5file": h5file,
                 "h5mode": "w",
                 "identifier": self.identifier
                 }

        with flimage.FLSeries(**qpskw) as fls:
            for ii in range(len(self)):
                fli = self.get_flimage(ii)
                fls.add_flimage(fli)


def hash_obj(data, maxlen=5):
    hasher = hashlib.md5()
    tohash = obj2bytes(data)
    hasher.update(tohash)
    return hasher.hexdigest()[:maxlen]


def obj2bytes(data):
    tohash = []
    if isinstance(data, (tuple, list)):
        for item in data:
            tohash.append(obj2bytes(item))
    elif isinstance(data, str):
        tohash.append(data.encode("utf-8"))
    elif isinstance(data, bytes):
        tohash.append(data)
    elif isinstance(data, np.ndarray):
        tohash.append(data.tobytes())
    else:
        msg = "No rule to convert to bytes: {}".format(data)
        raise NotImplementedError(msg)
    return b"".join(tohash)

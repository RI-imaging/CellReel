"""Importing this module will register a custom formats in qpformat"""
import copy
import functools
import pathlib
import tempfile
import shutil
import warnings
import zipfile


import numpy as np
import qpimage
import qpformat.file_formats
from qpformat.file_formats.single_tif_phasics import INTENSITY_BASELINE_CLAMP


class SingleGuck(qpformat.file_formats.SingleData):
    """Single txt-based phase/intensity files
    """
    storage_type = "phase,intensity"

    def get_qpimage_raw(self, idx=0):
        """Return QPImage without background correction"""
        # Load experimental data
        if "wavelength" in self.meta_data:
            wlnm = self.meta_data["wavelength"] * 1e9
        else:
            wlnm = 550
            warnings.warn("Guessing wavelength of 550nm for '{}'!".format(
                self.path))
        phase, inten = load_phase_intensity(self.path, wavelength_nm=wlnm)
        inten[inten < 0] = 0
        meta_data = copy.copy(self.meta_data)
        qpi = qpimage.QPImage(data=(phase, inten),
                              which_data="phase,intensity",
                              meta_data=meta_data,
                              h5dtype=self.as_type)
        # set identifier
        qpi["identifier"] = self.get_identifier()
        return qpi

    @staticmethod
    def verify(path):
        """Verify that `path` is a phasics phase/intensity TIFF file"""
        valid = False
        try:
            pi = path.with_suffix(".tif_intensity")
            if path.suffix == ".tif_phase" and pi.exists():
                valid = True
        except (ValueError, IsADirectoryError):
            pass
        return valid


class SeriesZipGuck(qpformat.file_formats.SeriesData):
    """Custom Guck-lab zip file with phase and intensity txt files

    The data are stored as text files in a zip file.
    """
    storage_type = "phase,intensity"

    def __init__(self, *args, **kwargs):
        super(SeriesZipGuck, self).__init__(*args, **kwargs)
        self._files = None
        self._dataset = None

    def __len__(self):
        return len(self.files)

    def _get_dataset(self, idx):
        # Use ``zipfile.ZipFile.open`` to return an open file
        zf = zipfile.ZipFile(self.path)
        tdir = tempfile.mkdtemp()
        zf.extract(self.files[idx], tdir)
        zf.extract(self.files[idx][:-5]+"intensity", tdir)
        path = pathlib.Path(tdir) / self.files[idx]
        ds = SingleGuck(path=path,
                        meta_data=self.meta_data)
        return ds, tdir

    @staticmethod
    @functools.lru_cache(maxsize=32)
    def _index_files(path):
        """Search zip file for _phase files"""
        with zipfile.ZipFile(path) as zf:
            names = sorted(zf.namelist())
            names = [nn for nn in names if nn.endswith(".tif_phase")]
            names = [nn for nn in names if nn.startswith("SID")]
            return names

    @property
    def files(self):
        """List of Phasics tif file names in the input zip file"""
        if self._files is None:
            self._files = SeriesZipGuck._index_files(self.path)
        return self._files

    def get_qpimage_raw(self, idx):
        """Return QPImage without background correction"""
        ds, tdir = self._get_dataset(idx)
        qpi = ds.get_qpimage_raw()
        qpi["identifier"] = self.get_identifier(idx)
        qpi["time"] = self.get_time(idx)
        shutil.rmtree(tdir, ignore_errors=True)
        return qpi

    def get_time(self, idx):
        # Obtain the time from the text file name
        name = self.files[idx]
        _, _, t1 = name.split()
        t2, t3, _ = t1.split(".")
        h, m, s = t2.strip("-").split("_")
        us = t3
        return int(h)*60*60 + int(m) * 60 + int(s) + int(us)*1e-5

    @staticmethod
    def verify(path):
        """Verify that `path` is a zip file with Phasics TIFF files"""
        valid = False
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipfile, IsADirectoryError):
            pass
        else:
            names = sorted(zf.namelist())
            names = [nn for nn in names if nn.startswith("SID")]
            names1 = [nn for nn in names if nn.endswith(".tif_phase")]
            names2 = [nn for nn in names if nn.endswith(".tif_intensity")]
            if names1 and len(names1) == len(names2):
                valid = True
            zf.close()
        return valid


def load_file(path):
    """Load a txt data file"""
    path = pathlib.Path(path)
    data = path.open().readlines()
    # remove comments and empty lines
    data = [ll for ll in data if len(ll.strip()) and not ll.startswith("#")]
    # determine data shape
    n = len(data)
    m = len(data[0].strip().split())
    res = np.zeros((n, m), dtype=np.dtype(float))
    # write data to array, replacing comma with point decimal separator
    for ii in range(n):
        res[ii] = np.array(data[ii].strip().replace(",", ".").split(),
                           dtype=float)
    return res[::-1, :]


def load_phase_intensity(path, wavelength_nm):
    """Load QPI data using *tif_phase files"""
    path = pathlib.Path(path)
    phase = load_file(path)*550/wavelength_nm*2*np.pi
    inten = load_file(path.with_suffix(".tif_intensity"))
    return phase, inten - INTENSITY_BASELINE_CLAMP


def register_custom_formats():
    # register new file formats
    qpformat.file_formats.formats.insert(0, SingleGuck)
    qpformat.file_formats.formats.insert(0, SeriesZipGuck)

    for fmt in [SingleGuck, SeriesZipGuck]:
        qpformat.file_formats.formats_dict[fmt.__name__] = fmt

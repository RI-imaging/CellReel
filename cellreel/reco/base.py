import abc

import h5py
import numpy as np
import odtbrain

from . import pp_apple
from ..sino import rot


class Reconstruction(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, sv, rotation_name, kwargs={}):
        self.sv = sv
        self.path = self.sv.path.parent
        self.rotation_name = rotation_name
        self.kwargs = kwargs

        # initialize rotation
        self.hash_sino = sv.get_hash()
        self.hash_rot = rot.get_hash(self.path, rotation_name)
        states = rot.load_rotation_states(self.path)
        self.state_rot = states[rotation_name]["children"]

        # start and end frames
        axis_roll = np.deg2rad(self.state_rot["Roll"]["value"])
        self.tilted_axis = [np.cos(axis_roll), -np.sin(axis_roll), 0]

    def get_angles_slice(self, mode="phase"):
        """Return angles and corresponding sinogram slice

        Parameters
        ----------
        mode: str
            Imaging modality (fluorescence, phase, amplitude)

        Returns
        -------
        angles: 1d ndarray
            Sinogram angles
        angle_slice: slice
            Slice of the sinogram (with imaging modality `mode`)
            corresponding to `angles`.
        """
        t_start = self.state_rot["Start"]["value"]
        t_end = self.state_rot["End"]["value"]
        angle_slice = self.sv.get_time_slice(t_start, t_end, mode)
        spacing = self.state_rot["Spacing"]["value"]

        if spacing == "2PI uniform":
            # This is more accurate than an equal distribution between
            # 0 and 2PI, because t_start and t_end are given with
            # sub-pixel accuracy. It also makes sure the fluorescence and
            # refractive index are aligned temporarily/angularly.
            duration = t_end - t_start
            times = self.sv.get_times(mode=mode)
            angles = (times[angle_slice] - t_start) / duration * 2*np.pi
        else:
            ref_ang = rot.compute_angles_from_spacing(path=self.path,
                                                      spacing=spacing,
                                                      sv=self.sv,
                                                      mode="phase")

            angles = rot.compute_angles_from_spacing(path=self.path,
                                                     spacing=spacing,
                                                     sv=self.sv,
                                                     mode=mode) - ref_ang[0]

        return angles, angle_slice

    def get_sinogram(self, which="rytov"):
        assert which in ["fluorescence", "phase", "rytov"]
        if which in ["phase", "rytov"]:
            angles, angle_slice = self.get_angles_slice(mode="phase")
        else:
            angles, angle_slice = self.get_angles_slice(mode="fluorescence")
        if which == "rytov":
            amp = self.sv.amp[angle_slice]
            pha = self.sv.pha[angle_slice]
            field = amp * np.exp(1j*pha)
            sino = odtbrain.sinogram_as_rytov(uSin=field)
        elif which == "phase":
            sino = self.sv.pha[angle_slice]
        elif which == "fluorescence":
            sino = self.sv.fl[angle_slice]
        return sino, angles


class FLReconstruction(Reconstruction):
    def get_schemes(self):
        return {"standard": {}}

    @abc.abstractmethod
    def reconstruct_fluorescence(self, scheme="standard", count=None,
                                 max_count=None):
        """Perform reconstruction, override in subclass"""

    def run(self, scheme="standard", count_rec=None, max_count_rec=None):
        fl, info = self.reconstruct_object_function(scheme=scheme,
                                                    count=count_rec,
                                                    max_count=max_count_rec,
                                                    )
        info["max"] = fl.real.max()
        info["min"] = fl.real.min()

        return fl, info


class QPReconstruction(Reconstruction):
    def get_schemes(self):
        return {"standard": {}}

    @abc.abstractmethod
    def post_process(self, f):
        """Post-processing, override in subclass"""

    @abc.abstractmethod
    def reconstruct_object_function(self, scheme="standard", count=None,
                                    max_count=None):
        """Perform reconstruction, override in subclass"""

    def run(self, scheme="standard", apple_core_correction=None,
            count_rec=None, max_count_rec=None,
            count_pp=None, max_count_pp=None):
        meta = self.sv.meta

        if max_count_rec is not None:
            max_count_rec.value += 1

        # Cache object function in session "cache" folder
        cache_name = "{}_{}_{}_{}.h5".format(type(self).__name__,
                                             self.hash_sino[:5],
                                             self.hash_rot[:5],
                                             scheme)
        cache_path = self.path / "cache" / cache_name
        cache_path.parent.mkdir(exist_ok=True)
        if cache_path.exists():
            # use cached object function
            with h5py.File(cache_path, "r") as h5:
                f = h5["data"][:]
                info = dict(h5.attrs)
        else:
            # compute object function
            f, info = self.reconstruct_object_function(scheme=scheme,
                                                       count=count_rec,
                                                       max_count=max_count_rec)
            # cache object function
            with h5py.File(cache_path, "w") as h5:
                h5["data"] = f
                h5.attrs.update(info)

        if count_rec is not None:
            count_rec.value += 1

        # apple core correction / post-processing
        if max_count_pp is not None:
            max_count_pp.value += 1

        if apple_core_correction:
            fc, info2 = pp_apple.correct(f=f,
                                         meta=meta,
                                         count=count_pp,
                                         max_count=max_count_pp,
                                         method=apple_core_correction)
        else:
            fc = f
            info2 = {}

        ri, info3 = self.post_process(f=fc)

        if count_pp is not None:
            count_pp.value += 1

        info.update(info2)
        info.update(info3)

        info["real max"] = ri.real.max()
        info["real min"] = ri.real.min()
        info["imag max"] = ri.imag.max()
        info["imag min"] = ri.imag.min()

        return ri, info

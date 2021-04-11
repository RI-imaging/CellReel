import odtbrain
import radontea

from ..sino.rot import rotate_sinogram
from .base import QPReconstruction


class BPJradontea(QPReconstruction):
    def post_process(self, f):
        meta = self.sv.meta

        ri = odtbrain.opt_to_ri(f,
                                res=meta["wavelength"]/meta["pixel size"],
                                nm=meta["medium index"])

        info = {}
        return ri, info

    def reconstruct_object_function(self, scheme="standarad", count=None,
                                    max_count=None):
        """Wrapper for radontea reconstruction"""
        sino, angles = self.get_sinogram(which="phase")

        func = radontea.backproject_3d
        sinorot = rotate_sinogram(sino, self.tilted_axis, fillval=0)
        f = func(sinogram=sinorot,
                 angles=angles,
                 count=count,
                 max_count=max_count,
                 )

        info = {"library": "radontea {}".format(radontea.__version__),
                "library function": func.__name__,
                "algorithm": "BPJ",
                }

        return f, info

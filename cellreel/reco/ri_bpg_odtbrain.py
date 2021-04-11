from collections import OrderedDict

import odtbrain

from .base import QPReconstruction


SCHEMES = OrderedDict()

SCHEMES["low precision"] = {
    "onlyreal": True,
    "padding": (False, False),
    "padfac": 1,  # has no effect when padding is disabled
    "padval": "edge",  # has no effect when padding is disabled
    "intp_order": 0,
    "dtype": "float32",
}

SCHEMES["standard"] = {
    "onlyreal": True,
    "padding": (True, True),
    "padfac": 1.75,
    "padval": "edge",
    "intp_order": 1,  # 1 has no visible effect (20%)
    "dtype": "float32"  # has no visible effect (5-10%)
}

SCHEMES["high precision"] = {
    "onlyreal": False,
    "padding": (True, True),
    "padfac": 2.1,  # corrects for offset
    "padval": 0,
    "intp_order": 2,
    "dtype": "float64",
}


class BPGodtbrain(QPReconstruction):
    def get_schemes(self):
        return SCHEMES.copy()

    def post_process(self, f):
        meta = self.sv.meta
        ri = odtbrain.odt_to_ri(f=f,
                                res=meta["wavelength"]/meta["pixel size"],
                                nm=meta["medium index"])
        info = {}
        return ri, info

    def reconstruct_object_function(self, scheme="standarad", count=None,
                                    max_count=None):
        """Wrapper for ODTbrain reconstruction"""
        meta = self.sv.meta
        # custom function arguments
        opts = {"res": meta["wavelength"]/meta["pixel size"],
                "nm": meta["medium index"],
                }
        kwargs = self.get_schemes()[scheme]
        opts.update(kwargs)
        # function
        if True:  # not np.all(np.array(tilted_axis) == np.array([0, 1, 0])):
            # take into account rotational axis
            func = odtbrain.backpropagate_3d_tilted
            opts["tilted_axis"] = self.tilted_axis
        else:
            # use faster algorithm
            func = odtbrain.backpropagate_3d
        # function keyword arguments
        sino, angles = self.get_sinogram(which="rytov")
        funckw = {"uSin": sino,
                  "angles": angles,
                  "count": count,
                  "max_count": max_count}
        funckw.update(opts)
        # special keyword arguments
        if "save_memory" in self.kwargs:
            funckw["save_memory"] = self.kwargs["save_memory"]

        # compute potential
        f = func(**funckw)

        info = {"library": "ODTbrain {}".format(odtbrain.__version__),
                "library function": func.__name__,
                "algorithm": "BPG",
                }
        for key in opts:
            info["kw {}".format(key)] = opts[key]

        return f, info

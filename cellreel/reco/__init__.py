import collections

from .ri_bpg_odtbrain import BPGodtbrain
from .ri_bpj_radontea import BPJradontea
from .fl_bpj_radontea import FLBPJradontea


#: Available reconstruction algorithms for diffraction tomography
ri_algs = collections.OrderedDict()
ri_algs["BPG (ODTbrain)"] = BPGodtbrain
ri_algs["BPJ (radontea)"] = BPJradontea


fl_algs = collections.OrderedDict()
fl_algs["BPJ (radontea)"] = FLBPJradontea


#: Available reconstruction algorithms for diffraction tomography
post_algs = collections.OrderedDict()
post_algs["Keep Apple Core"] = None
post_algs["Fill Apple Core (NN)"] = "nn"
post_algs["Fill Apple Core (SH)"] = "sh"

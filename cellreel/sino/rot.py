import collections
import hashlib
import json

import lmfit
import numpy as np
from pyqtgraph.parametertree import Parameter
from scipy.ndimage import rotate


from .util import obj2bytes


#: Default rotation parameters
params = [
    {'name': 'Start', 'type': 'float', 'value': 0, 'step': .1,
     'decimals': 5, 'siPrefix': False, 'suffix': 's'},
    {'name': 'End', 'type': 'float', 'value': 0, 'step': .1,
     'decimals': 5, 'siPrefix': False, 'suffix': 's'},
    {'name': 'Roll', 'type': 'float', 'value': 0, 'step': 1,
     'decimals': 5, 'siPrefix': False, 'suffix': '°'},
    {'name': 'Spacing', 'type': 'list',
     'values': ["2PI uniform"], 'value': "2PI uniform"},
]


def angle_project_2pi(signal, offset, amplitude):
    """
    Given a sinosoidal-like signal covering a range of 2PI,
    determine the rotational angle horizontally projecting the
    signal values onto a sinusoidal curve.

    Parameters
    ----------
    signal: 1d ndarray
        Sinusoidal-like curve
    offset: float
        Vertical offset of the curves.
    amplitude: float
        Ampltitude of the sinosoidal curve.

    Returns
    -------
    angles : 1d ndarray
        The respective angles in the the sine curve determined
        by projection of the values in offset onto a sine curve
        and determining the arccos.

    Notes
    -----
    Input data must be from a 2PI rotation.

    The inflection points are assumed to be where the min and the max
    of the input array are.
    """
    y_values = signal.copy()

    # normalize data
    y_values = (y_values - offset)/amplitude

    idmax = np.argmax(y_values)

    # roll the entire array such that the max value is at the left
    off = np.roll(y_values, -idmax)

    # first halve (all points up to but not including the minimum):
    angles = []
    for ii in range(np.argmin(off)):
        angles.append(np.arccos(off[ii]))

    for ii in range(np.argmin(off), off.size):
        angles.append(np.arccos(-off[ii])+np.pi)

    retangles = np.roll(angles, idmax)
    retangles = np.unwrap(retangles)
    return retangles


def compute_angles_from_spacing(path, spacing, sv, mode):
    """Fit a skewed periodic and compute the rotation angles

    This is a convenience function that wraps around
    :func:`load_spacing_states`,  :func:`fit_skewed_periodic`
    and :func:`angle_project_2pi`.

    The parameters are identical to that of :func:`fit_main_periodic`.
    """
    sp = load_spacing_states(path)[spacing]

    data = np.array(sp["points"])
    func, params = fit_skewed_periodic(x=data[:, 1],
                                       y=data[:, 0],
                                       period=sp["period"],
                                       num_skw=sp["num_skw"],
                                       y0=sp["y0"])
    tslice = sv.get_time_slice(sp["t_start"], sp["t_end"], mode=mode)
    xp = sv.get_times(mode=mode)[tslice] - sp["t0"]
    yp = func(xp)

    offset = params["y0"]
    ampltidue = params["a"]
    angles = angle_project_2pi(signal=yp, offset=offset, amplitude=ampltidue)
    return angles


def fit_skewed_periodic(x, y, period, num_skw=2, y0=None):
    """Fit a skewed periodic function

    Parameters
    ----------
    x: 1D ndarray
        x-coordinates for fitting
    y: 2D ndarray
        y-coordinates that are fitted
    period: float
        Period of the periodic function.
    num_skw: int
        Number of skewing coefficients (modulation terms) in the
        fit function (see :func:`skewed_periodic_model`).
    y0: float
        Initial offset in y-direction. Defaults to the
        average of the y coordinates if not set!

    Returns
    -------
    func: callable
        A function that computes the fitted curve when
        given the argument x.
    params: dict
        Dictionary holding the fit results.
    """
    params = lmfit.Parameters()

    if y0 is None:
        y0 = np.average(y)

    params.add("f", value=1/period, vary=False)

    yamp = y.max() - y0
    params.add("x0", value=0, min=-2*np.pi, max=2*np.pi)
    params.add("y0", value=y0, vary=True)
    params.add("a", value=yamp, max=yamp*1.2, min=yamp*.8)

    # Initial fit to get better starting parameters
    outi = lmfit.minimize(skewed_periodic_residual, params, args=(x, y))
    params = outi.params

    for ii in range(num_skw):
        params.add("b{}".format(ii), value=0)
        params.add("c{}".format(ii), value=0)

    out = lmfit.minimize(skewed_periodic_residual, params, args=(x, y))

    if False:
        import matplotlib.pylab as plt
        x2 = np.linspace(0, period, 100, endpoint=True)
        y2 = skewed_periodic_model(out.params, x2)
        for key in out.params.keys():
            print(key, out.params[key].value)
        plt.plot(x, y, "o", label="data")
        plt.plot(x2, y2, "x-", label="fit")
        plt.legend()
        plt.grid()
        plt.show()

    def func(x): return skewed_periodic_model(out.params, x)

    return func, out.params.valuesdict()


def get_default_rotation_params():
    """Return default parameters for rotation identification"""
    ps = Parameter.create(name='params',
                          type='group',
                          children=params)
    return ps


def get_hash(path, name):
    """Compute a hash for a given rotation state"""
    state = load_rotation_states(path)[name]["children"]
    spacings = load_spacing_states(path)
    hasher = hashlib.md5()
    for key in state:  # state is ordered dict
        if key == "Spacing" and state["Spacing"]["value"] != "2PI uniform":
            space = spacings[state["Spacing"]["value"]]
            for kk in sorted(space.keys()):
                hasher.update(obj2bytes(space[kk]))
        else:
            hasher.update(obj2bytes(state[key]["value"]))
    return hasher.hexdigest()


def load_rotation_states(path):
    """Return rotation states of a CellReel session path as dict"""
    rp = path / "rotations.txt"
    p = get_default_rotation_params()
    # add spacings
    sp = load_spacing_states(path)
    if sp:
        cc = p.child("Spacing")
        limits = cc.opts["values"] + sorted(sp.keys())
        cc.setLimits(limits)
    # populate dictionary
    ddict = collections.OrderedDict()
    if rp.exists():
        with rp.open("r") as fp:
            save_dict = json.load(fp)

        for name in save_dict:
            sdict = save_dict[name]
            for key in sdict:
                p.child(key).setValue(sdict[key])
            ddict[name] = p.saveState()
    return ddict


def load_spacing_states(path):
    """Load user-defined spacings from a project directory"""
    rp = path / "spacings.txt"

    if rp.exists():
        with rp.open("r") as fp:
            save_dict = json.load(fp)
    else:
        save_dict = {}
    return save_dict


def save_rotation_states(path, state_dict):
    """Save rotation states to a session path"""
    rp = path / "rotations.txt"
    p = get_default_rotation_params()
    save_dict = collections.OrderedDict()
    for name in state_dict:
        p.restoreState(state_dict[name])
        sdict = {}
        for ch in p.children():
            sdict[ch.name()] = ch.value()
        save_dict[name] = sdict
    with rp.open("w") as fp:
        json.dump(save_dict, fp, indent=2)


def save_spacing_state(path, name, points, period, num_skw, y0, t0,
                       t_start, t_end, user_slice, user_mode):
    """Save user-defined spacings to a project directory"""
    rp = path / "spacings.txt"
    save_dict = load_spacing_states(path)
    save_dict[name] = {"points": points,
                       "period": period,
                       "num_skw": num_skw,
                       "y0": y0,
                       "t0": t0,
                       "t_start": t_start,
                       "t_end": t_end,
                       "user_slice": user_slice,
                       "user_mode": user_mode}

    with rp.open("w") as fp:
        json.dump(save_dict, fp, indent=2)


def rotate_sinogram(data, tilted_axis, fillval=0):
    angle = np.arctan2(tilted_axis[0], tilted_axis[1])
    output = rotate(input=data,
                    angle=np.rad2deg(angle),
                    axes=(1, 2),
                    reshape=False,
                    order=3,
                    mode="constant",
                    cval=fillval,
                    )
    return output


def save_spacing_states(path, save_dict):
    # remove existing states
    rp = path / "spacings.txt"
    rp.unlink()
    for dd in save_dict:
        save_spacing_state(path=path,
                           name=dd,
                           **save_dict[dd])


def skewed_periodic_model(params, x):
    """Fit model for a skewed periodic function for lmfit

    A periodic function that is modulated by sine functions

    periodic = a * sin(x-x0 + sum_n sin(bn*n*x-cn) + y0

    Parameters
    ----------
    params: lmfit.Parameters
        At least the Parameters Amplitude "a", frequency "f", and
        initial position in x "x0" and y "y0" must be given. For
        a skewed periodic, add the parameters "bn" and "cn" with
        the number of skewing coefficients "n".
    x: 1D ndarray
        x - values of the periodic

    Returns
    -------
    periodic: 1D ndarray
        evaluated periodic function

    """
    a = params["a"].value
    f = params["f"].value
    x0 = params["x0"].value
    y0 = params["y0"].value

    bn = []
    b_keys = [k for k in list(params.keys()) if k.startswith("b")]
    b_keys.sort()
    for b in b_keys:
        bn.append(params[b].value)

    on = []
    o_keys = [k for k in list(params.keys()) if k.startswith("c")]
    o_keys.sort()
    for o in o_keys:
        on.append(params[o].value)

    w = 2*np.pi*f

    modulation = np.zeros_like(x)
    for ii in range(len(bn)):
        modulation += bn[ii]*np.sin((ii+1)*w*x - on[ii])
    mdl = y0 + a*np.sin(w*x - x0 + modulation)

    return mdl


def skewed_periodic_residual(params, x, data):
    """Fit residuals of skewed periodic function for lmfit"""
    mdl = skewed_periodic_model(params, x)
    return mdl-data

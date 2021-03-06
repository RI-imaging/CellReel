import hashlib

import numpy as np


def hash_object(obj):
    """Compute sha256 hex-hash of a Python object

    Objects in dicts/lists/tuples are joined together before hashing
    using :func:`obj2bytes` in this module.

    Returns
    -------
    hex: str
        The first six characters of the hash
    """
    ihasher = hashlib.sha256()
    ihasher.update(obj2bytes(obj))
    return ihasher.hexdigest()[:6]


def obj2bytes(obj):
    """String representation of an object for hashing"""
    if isinstance(obj, str):
        return obj.encode("utf-8")
    elif isinstance(obj, (bool, int, float)):
        return str(obj).encode("utf-8")
    elif obj is None:
        return b"none"
    elif isinstance(obj, np.ndarray):
        return obj.tostring()
    elif isinstance(obj, tuple):
        return obj2bytes(list(obj))
    elif isinstance(obj, list):
        return b"".join(obj2bytes(o) for o in obj)
    elif isinstance(obj, dict):
        return obj2bytes(sorted(list(obj.items())))
    else:
        raise ValueError("No rule to convert object '{}' to bytes.".
                         format(obj.__class__))

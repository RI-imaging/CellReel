"""Save and load meta data hints for experimental data on disk"""
import json
import os
import pathlib


def get_path_meta(path_qpi):
    path_qpi = pathlib.Path(path_qpi)
    path_meta = path_qpi.with_name(path_qpi.name + "_CellReel.hints")
    return path_meta


def load_hints(path_qpi):
    """Returns all possible meta data information"""
    root = pathlib.Path(path_qpi).parent
    rp = get_path_meta(path_qpi)
    hints = {}
    if rp.exists():
        with rp.open("r") as fp:
            try:
                hints = json.load(fp)
            except json.decoder.JSONDecodeError:
                # something went wrong during saving, ignore
                pass
            else:
                for key in hints:
                    # convert path strings to Path
                    if key.startswith("path"):
                        p1 = (root / hints[key])
                        if p1.exists():
                            hints[key] = p1.resolve()
                        else:
                            # backwards compatibility (no relative path)
                            hints[key] = pathlib.Path(hints[key])
    return hints


def save_hints(path_qpi, hints):
    """Saves all hints to a file in the directory of `path_qpi`"""
    root = pathlib.Path(path_qpi).parent
    for key in sorted(hints.keys()):
        # convert Path to string
        if key.startswith("path"):
            if hints[key] is None:
                hints.pop(key)
            else:
                hints[key] = os.path.relpath(hints[key], root)
    rp = get_path_meta(path_qpi)
    try:
        with rp.open("w") as fp:
            json.dump(hints, fp, indent=2)
    except OSError:
        # readonly or somesuch
        pass

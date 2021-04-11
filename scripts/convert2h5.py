"""Convert original data to the HDF5 format (flseries/qpseries)"""
import pathlib
import sys

import cellreel.wiz_init
import qpformat


if __name__ == "__main__":
    path_in = pathlib.Path(sys.argv[-1])
    path_out = path_in.parent.with_suffix(".converted")
    path_out.mkdir(exist_ok=True)

    hints = cellreel.wiz_init.meta_hints.load_hints(path_in)

    # QPI
    meta_qpi = {"pixel size": hints["pixel size"]*1e-6,
                "wavelength": hints["wavelength"]*1e-9,
                "medium index": hints["medium index"],
                }

    # reference
    if "path_reference_qpi" in hints:
        refqpi = qpformat.load_data(hints["path_reference_qpi"],
                                    meta_data=meta_qpi,
                                    ).get_qpimage()
        refqpi.copy(path_out / "reference_qpi.h5")

    # main data
    ds_qpi = qpformat.load_data(path_in,
                                bg_data=hints["path_qpi_bg"],
                                meta_data=meta_qpi,
                                )
    ds_qpi.saveh5(h5file=path_out / "sinogram_qpi.h5")

    # FL
    if "path_reference_fli" in hints:
        meta_fli = {"pixel size": hints["pixel size fl"]*1e-6}

        # reference
        reffli = cellreel.wiz_init.flformat.load_data(
            hints["path_reference_fli"], meta_data=meta_fli).get_flimage()
        reffli.copy(path_out / "reference_fli.h5")

        ds_fli = cellreel.wiz_init.flformat.load_data(hints["path_fl"],
                                                      meta_data=meta_fli)
        ds_fli.saveh5(h5file=path_out / "sinogram_fli.h5")

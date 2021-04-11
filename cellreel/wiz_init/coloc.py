"""Fluorescence to QPI colocalization"""
from skimage.transform import warp


# field_x,216.48
# field_y,105.06
# fluor_x,597.5856
# fluor_y,507.936
# field_res,0.139
# fluor_res,0.091


def transform_function(output_coords,
                       p_qp=(0, 0),
                       p_fl=(0, 0),
                       res_qp=1,
                       res_fl=1):
    """Returns an image with array fluor aligned to array field

    Adapted from old analysis pipeline

    Parameters
    ----------
    output_coords: 2d ndarray of shape (P, 2)
        array of (col, row) coordinates in the output image

    Returns
    -------
    input_coords: 2d ndarray of shape (P, 2)
        corresponding coordinates in the input image
    """
    input_coords = output_coords.copy()
    xi = input_coords[:, 0]
    yi = input_coords[:, 1]

    xi[:] = (xi - p_qp[0])*res_qp / res_fl + p_fl[0]
    yi[:] = (yi - p_qp[1])*res_qp / res_fl + p_fl[1]

    return input_coords


def warp_fl(fl, p_qp, p_fl, res_qp, res_fl, output_shape):
    flc = warp(image=fl,
               inverse_map=transform_function,
               map_args={"p_qp": p_qp,
                         "p_fl": p_fl,
                         "res_qp": res_qp,
                         "res_fl": res_fl
                         },
               output_shape=output_shape,
               )
    return flc

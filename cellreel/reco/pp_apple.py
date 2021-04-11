import odtbrain


def correct(f, meta, count, max_count, method):
    """Basic apple core correction"""
    corr = odtbrain.apple.correct(f=f,
                                  res=meta["wavelength"]/meta["pixel size"],
                                  nm=meta["medium index"],
                                  method=method,
                                  count=count,
                                  max_count=max_count)

    # apple core correction (non-negativity)
    info = {"apple core correction": "apple-{}".format(method.upper())}
    return corr, info

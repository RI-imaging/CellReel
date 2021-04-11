from os.path import dirname, realpath, exists
from setuptools import setup
import sys


author = u"Paul Müller"
authors = [author]
descr = 'graphical user interface for refractive index and " \
        + fluorescence tomography'
name = 'cellreel'
year = "2021"

sys.path.insert(0, realpath(dirname(__file__))+"/"+name)
from _version import version  # noqa: E402

setup(
    name=name,
    author=author,
    author_email='dev@craban.de',
    url='https://github.com/RI-imaging/CellReel',
    version=version,
    packages=[name],
    package_dir={name: name},
    license="GPL v3",
    description=descr,
    long_description=open('README.rst').read() if exists('README.rst') else '',
    install_requires=[
        "appdirs",  # user config
        "cellsino>=0.4.0",  # artificial sinogram generation
        "flimage",  # FL data management
        "h5py>=2.7",  # data storage
        "imageio[ffmpeg]>=2.5"  # avi import (fl)/export
        "matplotlib>=3.0",  # color maps
        "numpy",
        "odtbrain>=0.4.0",  # ODT reconstruction
        "pyqt5",
        "pyqtgraph==0.12.1",  # visualization
        "qpformat>=0.10.8",  # loading QPI data
        "qpimage>=0.5.2",  # QPI data management
        "radontea>=0.4.1",  # OPT reconstruction
        "scikit-image>=0.11.0",  # series alignment
        "tifffile",  # loading single fluorescence images
        ],
    python_requires='>=3.6, <4',
    keywords=["digital holographic microscopy",
              "tomography",
              "diffraction tomography",
              "fluorescence tomography",
              "quantitative phase imaging",
              "refractive index",
              ],
    classifiers=[
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Intended Audience :: Science/Research'
    ],
    platforms=['ALL'],
)

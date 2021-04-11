import hashlib
import json
import multiprocessing as mp
import pathlib
import pkg_resources
import time
import urllib.request

from PyQt5 import QtCore, QtWidgets


class DownloadThread(QtCore.QThread):
    def __init__(self, data, path, count, max_count, *args, **kwargs):
        super(DownloadThread, self).__init__(*args, **kwargs)
        self.data = data
        self.path = path
        self.count = count
        self.max_count = max_count

    def run(self, init=True):
        if init:
            with self.max_count.get_lock():
                self.max_count.value += self.data["size"]
                self.max_count.value += self.data["size"] // 50
        download(url=self.data["urls"][0],
                 path=self.path,
                 total_size=self.data["size"],
                 count=self.count)

        if verify_checksum(path=self.path, sha256sum=self.data["sha256"]):
            with self.count.get_lock():
                self.count.value += self.data["size"] // 50
        else:
            self.path.unlink()
            with self.count.get_lock():
                self.count.value -= self.data["size"]
            self.run(retry=True)


def download(url, path, resume=True, chunk_size=65536, total_size=None,
             count=None, max_count=None):
    """Download a file (supports resuming)

    Parameters
    ----------
    url: str
        URL to download
    path: str or pathlib.Path
        Download file name
    resume: bool
        Whether to resume a previous download or start anew
    chunk_size: int
        Download chunk size in bytes
    total_size: int
        The total size of the file to download; If None, the
        file size is obtained from the url info
    count, max_count: multiprocessing.Value
        Can be used for tracking the download progress from an external
        thread or process
    """
    path = pathlib.Path(path)
    if path.exists():
        cur_size = path.stat().st_size
    else:
        cur_size = 0

    if total_size is None:
        meta = urllib.request.urlopen(url).info()
        total_size = int(meta.get("Content-Length"))

    if max_count is not None:
        with max_count.get_lock():
            max_count.value += total_size

    if count is not None:
        with count.get_lock():
            count.value += cur_size

    # check whether we already have the whole file
    if cur_size < total_size:
        req = urllib.request.Request(url)
        if resume and path.exists():
            req.add_header('Range', "bytes={}-".format(cur_size))
            mode = "ab"
        else:
            cur_size = 0
            mode = "wb"

        up = urllib.request.urlopen(req)
        meta = up.info()
        remaining_size = int(meta.get("Content-Length"))

        read_size = 0
        with path.open(mode) as fd:
            while read_size < remaining_size:
                buffer = up.read(chunk_size)
                fd.write(buffer)
                fd.flush()
                read_size += len(buffer)
                if count is not None:
                    with count.get_lock():
                        count.value += len(buffer)

    assert path.stat().st_size == total_size, path


def download_dataset_qt5(key, path, progressbar=None):
    """Qt5 Convenience function for downloading a dataset

    Parameters
    ----------
    key: str
        Key for the dataset listed in "online_data.json";
        see :func:`get_available_datasets`
    path: str or pathlib.Path
        Download folder
    progressbar: PyQt5.QtWidgets.QProgressBar
        Optional progressbar where to display download progress;
        If not given, a `QProgressDialog` is displayed.

    Notes
    -----
    If a dataset consists of multiple files, they are all downloaded
    at once. If the download is interrupted (e.g. due to program crash)
    and this function is called again with the same `key` and `path`
    arguments, then all downloads are resumed.
    """
    path = pathlib.Path(path)
    data = get_available_datasets()[key]
    count = mp.Value('I', 0, lock=True)
    max_count = mp.Value('I', 0, lock=True)

    if progressbar is None:
        bar = QtWidgets.QProgressDialog("Downloading '{}'...".format(key),
                                        "This button does nothing",
                                        count.value,
                                        max_count.value)
        bar.setCancelButton(None)
        bar.setMinimumDuration(0)
        bar.setAutoClose(True)
        bar.setWindowTitle("Simulation")
    else:
        bar = progressbar

    threads = []
    for dt in data["data"]:
        dlthread = DownloadThread(data=dt,
                                  path=path/dt["name"],
                                  count=count,
                                  max_count=max_count)
        dlthread.start()
        threads.append(dlthread)

    # Show a progress until computation is done
    while count.value == 0 or count.value < max_count.value:
        time.sleep(.05)
        wa_fact = 1000000  # work-around factor (supported max of ProgressBar)
        bar.setValue(count.value // wa_fact)
        bar.setMaximum(max_count.value // wa_fact)
        QtCore.QCoreApplication.instance().processEvents()

    # make sure the thread finishes
    for thr in threads:
        thr.wait()


def get_available_datasets():
    """Return all available datasets listed in "online_data.json"
    """
    path = pkg_resources.resource_filename("cellreel.wiz_init",
                                           "online_data.json")
    with pathlib.Path(path).open() as fd:
        data = json.load(fd)
    return data


def get_dataset_size(key):
    """Return the size of a dataset in bytes"""
    ds = get_available_datasets()[key]
    size = 0
    for dt in ds["data"]:
        size += dt["size"]
    return size


def verify_checksum(path, sha256sum, chunk_size=65536,
                    count=None, max_count=None):
    """Verify the checksum of a file

    Parameters
    ----------
    path: str or pathlib.Path
        Path of the file
    sha256sum: str
        SHA246 sum of the file
    chunk_size: int
        Chunk size for updating the hasher in bytes
    count, max_count: multiprocessing.Value
        Can be used for tracking the hashing progress from an external
        thread or process

    Returns
    -------
    valid: bool
        True, if the checksum matches
    """
    path = pathlib.Path(path)
    if max_count is not None:
        max_count.value += path.stat().st_size

    with path.open("rb") as fd:
        hasher = hashlib.sha256()
        while True:
            buffer = fd.read(chunk_size)
            hasher.update(buffer)
            if count is not None:
                count.value += len(buffer)
            if len(buffer) == 0:
                break

        newsum = hasher.hexdigest()
    if sha256sum != newsum:
        return False
    else:
        return True


if __name__ == "__main__":
    with pathlib.Path("online_data.json").open() as fd:
        data = json.load(fd)

    name = "/tmp/test.h5"
    download(data["hl60"]["data"][0]["urls"][0], name)
    verify_checksum(name, data["hl60"]["data"][0]["sha256"])

"""Atomic directory publication with an OS-enforced no-replace condition."""

import ctypes
import os
import sys
from pathlib import Path


def publish(source: Path, destination: Path) -> None:
    """Same-parent rename. Windows/Linux refuse files, directories and symlinks."""
    if source.parent != destination.parent:
        raise ValueError("atomic publication requires sibling directories")
    if os.name == "nt":
        os.rename(source, destination)
        return
    if sys.platform != "linux":
        raise OSError("atomic no-replace export is supported on Windows and Linux")
    library = ctypes.CDLL(None, use_errno=True)
    try:
        rename = library.renameat2
    except AttributeError as error:
        raise OSError("this Linux runtime lacks atomic no-replace renameat2") from error
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    # AT_FDCWD and RENAME_NOREPLACE; never fall back to a clobbering POSIX rename.
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(destination))

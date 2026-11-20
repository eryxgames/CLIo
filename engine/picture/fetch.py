# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""``clio.py --get-picture``: CLIo Picture's C library for this machine, from its GitHub release, into the
user's data folder - not into CLIo's folder or a game's.

The release is the one CLIo follows (``RELEASE``); its zip for this machine must match the SHA-256 noted here,
or nothing is installed. Only the library is taken out, with the LICENSE and NOTICE beside it. ``find_lib``
looks there after ``CLIO_PICTURE_LIB`` and a library put in ``engine/picture/lib/`` (a build of your own still
comes first).
"""
from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import sys
import urllib.request
import zipfile

RELEASE = "0.5.0"
URL = "https://github.com/eryxgames/clio-picture/releases/download/v{v}/clio-picture-{v}-{p}.zip"
SOURCE = "https://github.com/eryxgames/clio-picture"
SHA256 = {                      # from the release's checksums.txt
    "android-arm64-v8a": "d1a337a7a7b40ace042ab84a1ef764164164f288a79eeed7eaea5d083f7fd401",
    "android-armeabi-v7a": "bb00296fa2d62cf09809b31b8ee6419cc7b6b50756f02c1cc3b4b1967afc1eef",
    "android-x86_64": "18257d41444c4c2064bcdb0372ddb2f3023c70d7c1836ac5f60e309818cd477b",
    "linux-arm64": "ed88c67ebdca78a8f14630b728b38a030b0b7b76303895c58cdc2d2a5cc894f6",
    "linux-x64": "af10e02d83875852e9625cb075242d85f19dafdaed275be2b0a6d77e0be43c42",
    "macos-universal": "acb2fde5b6a22b9dba5bd103f1bdb8c15e0b6b3f5aaff1536e9a9b376d333859",
    "windows-arm64": "6ca88230e89c5f918364ea841089b5046202d809a268fbe27f82af3da649cb88",
    "windows-x64": "52a32a1d05000b1f5545fbfc6690dd6870561823fc5c7788eaf897fc2e4c14e0",
}


def library_name(plat):
    return "clio_picture.dll" if plat.startswith("windows") else "libclio_picture.dylib" \
        if plat.startswith("macos") else "libclio_picture.so"


def platform_name(sysplat=None, machine=None, android=None):
    """The release's name for this machine, or None if there is none for it."""
    from ..audio.ballistic import fetch as ballistic_fetch     # the same machines, the same names
    return ballistic_fetch.platform_name(sysplat, machine, android)


def home(env=None):
    """Where installed libraries live: CLIo's folder in the user's data (next to the saves)."""
    from ..audio.ballistic import fetch as ballistic_fetch
    return os.path.join(os.path.dirname(ballistic_fetch.home(env)), "picture")


def installed(env=None, plat=None):
    """The library --get-picture put here, or None."""
    plat = plat or platform_name()
    if not plat:
        return None
    path = os.path.join(home(env), RELEASE, library_name(plat))
    return path if os.path.isfile(path) else None


def get(out=print, env=None, plat=None, opener=None):
    """Download, check and install. Returns 0 when the library is in place and agrees with CLIo, 1 when not."""
    plat = plat or platform_name()
    if plat not in SHA256:
        out("CLIo Picture %s has no library listed for this machine (%s, %s). Build it from source (%s: make), "
            "then put it in engine/picture/lib/ or set CLIO_PICTURE_LIB to it. CLIo draws everything without it."
            % (RELEASE, plat or sys.platform, platform.machine(), SOURCE))
        return 1
    url = URL.format(v=RELEASE, p=plat)
    out("Downloading CLIo Picture %s for %s ..." % (RELEASE, plat))
    try:
        with (opener or urllib.request.urlopen)(url, timeout=120) as r:
            data = r.read()
    except Exception as e:                               # no network, a proxy, a missing file
        out("Could not download %s: %s" % (url, e))
        return 1
    if hashlib.sha256(data).hexdigest() != SHA256[plat]:
        out("The download does not match the checksum CLIo expects for %s: nothing was installed." % plat)
        return 1
    folder = os.path.join(home(env), RELEASE)
    name = library_name(plat)
    top = "clio-picture-%s-%s/" % (RELEASE, plat)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            files = {name: z.read(top + "lib/" + name)}
            for extra in ("LICENSE", "NOTICE"):
                if top + extra in z.namelist():
                    files[extra] = z.read(top + extra)
    except (KeyError, zipfile.BadZipFile) as e:
        out("The release's zip is not as expected (%s): nothing was installed." % e)
        return 1
    os.makedirs(folder, exist_ok=True)
    for fname, blob in files.items():
        path = os.path.join(folder, fname)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)
        if fname == name and os.name != "nt":
            os.chmod(path, 0o755)
    for old in os.listdir(home(env)):                    # an earlier release CLIo no longer follows
        p = os.path.join(home(env), old)
        if old != RELEASE and os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
    lib = os.path.join(folder, name)
    out("Installed %s" % lib)
    from . import check
    got, why = check(lib)
    if got is None:
        out("It is not used: %s" % why)
        return 1
    out("It loads and agrees with CLIo's Python: CLIo Picture %s. The first-person picture - the open land and "
        "its sky, rooms, walls, sprites, 3D models and the dots styles - is now drawn by it."
        % got.clio_picture_version().decode("ascii", "replace"))
    return 0

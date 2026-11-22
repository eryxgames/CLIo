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

RELEASE = "0.9.0"
URL = "https://github.com/eryxgames/clio-picture/releases/download/v{v}/clio-picture-{v}-{p}.zip"
SOURCE = "https://github.com/eryxgames/clio-picture"
SHA256 = {                      # from the release's checksums.txt
    "android-arm64-v8a": "2307f7795d91f7e22a9bf4a4b7317dd3a57e0d38ee356e8ddac050cd3fac6a9f",
    "android-armeabi-v7a": "2f4b86bcca751a408050e0e8b2dfe6963dc0e2a6256fdfe3768735c80343b099",
    "android-x86_64": "397d12ee5eeeb334b5204fedf724c7b3cbdfc836cf79f64050bd3d8f313dbba6",
    "linux-arm64": "8008dfae262a20b0bf4aafa4082b7ff0f30c5a6c83cddaf8dd94273106d6bd6c",
    "linux-x64": "90cfb01c6d00bade41aec3b3b3652d63664df2fc6243c5b63ad893147a23daf4",
    "macos-universal": "80931521b1fa5ed0dda11a949c8e3cb85a30566952deb210c9771194c80d14ea",
    "windows-arm64": "33d22c721b5c88f80040555773a0976283f8ad5adc31809cb361f3008f8f829e",
    "windows-x64": "6900138914b4c167d26624ec0615c51b7857a542cc03a7cab5f8120c009b6190",
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

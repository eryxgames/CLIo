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

RELEASE = "0.3.0"
URL = "https://github.com/eryxgames/clio-picture/releases/download/v{v}/clio-picture-{v}-{p}.zip"
SOURCE = "https://github.com/eryxgames/clio-picture"
SHA256 = {                      # from the release's checksums.txt
    "android-arm64-v8a": "65d9727db288acdc0e5875b8df2739c5353d7fe2227060bb5455bab06b810c13",
    "android-armeabi-v7a": "d275628116a68fd986abde1ab746cc81abab9d394828404944192b1ae523cc62",
    "android-x86_64": "67cda3eb15764fa24e3aeac89d4bb0c2faacee9ea1df3cabd0c35e66ec0ea562",
    "linux-arm64": "d3089998aa5a7beec9153e7e57cf57ece143812cc3ea4c93f361ecc261997e6a",
    "linux-x64": "ecf9d05a77c192dd59a6d67667d19732d634bb22f6d0a42178c30cfa6aadcc0a",
    "macos-universal": "619a4f285a98a0170cdff93e792b7fa2f72e9cd4751acffa51ba3bfc08bbca75",
    "windows-arm64": "7f87ff3cebc221c3fa1e5bece4a8229ed0c3575bbbcb4633574c58eafeee4556",
    "windows-x64": "94b731117406152522eb70f053077131966cfb7e2336856bba2218281a6ac510",
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
    out("It loads and agrees with CLIo's Python: CLIo Picture %s. The open land, its sky, the rooms' floors "
        "and the dots styles are now drawn by it." % got.clio_picture_version().decode("ascii", "replace"))
    return 0

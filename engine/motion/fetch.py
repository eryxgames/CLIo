# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""``clio.py --get-motion``: CLIo Motion's C library for this machine, from its GitHub release, into the user's
data folder - not into CLIo's folder or a game's.

The release is the one CLIo follows (``RELEASE``); its zip for this machine must match the SHA-256 noted here,
or nothing is installed. Only the library is taken out, with the LICENSE and NOTICE beside it. The library is
looked for there after ``CLIO_MOTION_LIB`` and one put in ``engine/motion/lib/`` (a build of your own still
comes first). Nothing needs it: without it bodies run live are stepped in Python.
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

RELEASE = "0.29.0"
URL = "https://github.com/eryxgames/clio-motion/releases/download/v{v}/clio-motion-{v}-{p}.zip"
SOURCE = "https://github.com/eryxgames/clio-motion"
SHA256 = {                      # from the release's checksums.txt
    "android-arm64-v8a": "29be7305747934e91320dc66ef650388903e67f3f3733077424ed6efedcd83ca",
    "android-armeabi-v7a": "5f6cc81a2b140d8ea3677b9bc8992d2b2a847e0f321b6b9540280383037d9644",
    "android-x86_64": "99491488bb1f83394c9f4ba1f52bc16029a592870af2c2da65961400bd6811ac",
    "linux-arm64": "abbc391412688b3642411d606b1a0f2fb908f3a2f1f789b4aa587cf262094d22",
    "linux-x64": "967559978e658d9ded8f08a826359f0cc605ab17cf41fbee31f55d384ef0e1f5",
    "macos-universal": "0739ff8f34a1524a8b434630f2cd9120b83b2925138333d926fdf112db5c4adf",
    "windows-arm64": "bf90b8870562f5b9598bf7b95ad7b25f9bd509d0875ed0405c40f2594d305188",
    "windows-x64": "c910f07b97bc9ed62b916aae30fa5a7414b9912d71574c5f0c96e4799c313874",
}


def library_name(plat):
    return "clio_motion.dll" if plat.startswith("windows") else "libclio_motion.dylib" \
        if plat.startswith("macos") else "libclio_motion.so"


def platform_name(sysplat=None, machine=None, android=None):
    """The release's name for this machine, or None if there is none for it."""
    from ..audio.ballistic import fetch as ballistic_fetch     # the same machines, the same names
    return ballistic_fetch.platform_name(sysplat, machine, android)


def home(env=None):
    """Where installed libraries live: CLIo's folder in the user's data (next to the saves)."""
    from ..audio.ballistic import fetch as ballistic_fetch
    return os.path.join(os.path.dirname(ballistic_fetch.home(env)), "motion")


def installed(env=None, plat=None):
    """The library --get-motion put here, or None."""
    plat = plat or platform_name()
    if not plat:
        return None
    path = os.path.join(home(env), RELEASE, library_name(plat))
    return path if os.path.isfile(path) else None


def get(out=print, env=None, plat=None, opener=None):
    """Download, check and install. Returns 0 when the library is in place and agrees with CLIo, 1 when not."""
    plat = plat or platform_name()
    if not SHA256:
        out("CLIo does not follow a release of CLIo Motion's library yet. Build it from source (%s: make -C c shared, "
            "or c\\build.bat), then put it in engine/motion/lib/ or set CLIO_MOTION_LIB to it. Bodies run live are "
            "stepped in Python without it." % SOURCE)
        return 1
    if plat not in SHA256:
        out("CLIo Motion %s has no library listed for this machine (%s, %s). Build it from source (%s: make -C c "
            "shared), then put it in engine/motion/lib/ or set CLIO_MOTION_LIB to it. Bodies run live are stepped "
            "in Python without it." % (RELEASE, plat or sys.platform, platform.machine(), SOURCE))
        return 1
    url = URL.format(v=RELEASE, p=plat)
    out("Downloading CLIo Motion %s for %s ..." % (RELEASE, plat))
    try:
        with (opener or urllib.request.urlopen)(url, timeout=120) as r:
            data = r.read()
    except Exception as e:                               # no network, a proxy, a missing file
        out("Could not download %s: %s" % (url, e))
        from .. import follow
        if follow.why(e):
            out(follow.why(e))
        return 1
    if hashlib.sha256(data).hexdigest() != SHA256[plat]:
        out("The download does not match the checksum CLIo expects for %s: nothing was installed." % plat)
        return 1
    folder = os.path.join(home(env), RELEASE)
    name = library_name(plat)
    top = "clio-motion-%s-%s/" % (RELEASE, plat)
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
    from .clio_motion import native
    got, why = native.check(lib)
    if got is None:
        out("It is not used: %s" % why)
        return 1
    native.use(True)                                     # looked for again, now that it is there
    out("It loads and agrees with CLIo's Python: CLIo Motion %s. Bodies run live (--crowd, a demo's crowds) are "
        "now stepped by it." % got.cm_version().decode("ascii", "replace"))
    return 0

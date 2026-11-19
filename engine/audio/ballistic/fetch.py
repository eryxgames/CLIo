"""``clio.py --get-ballistic``: Ballistic Engine's C library for this machine, from the engine's own GitHub
release, into the user's data folder - not into CLIo's folder or a game's.

The release is the one CLIo follows (``RELEASE``, the same Ballistic commit as ``engine.js``); its zip for
this machine must match the SHA-256 noted here, or nothing is installed. Only the library is taken out, with
the engine's LICENSE and NOTICE beside it. ``find_clib`` looks there after ``CLIO_BALLISTIC_LIB`` and a
library put in ``engine/audio/ballistic/lib/`` (a build of your own still comes first).
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

RELEASE = "0.5.0"          # Ballistic Engine 0.5.0 follows Ballistic 3603078, as engine.js does
URL = "https://github.com/eigensoundlab/ballistic-engine/releases/download/v{v}/ballistic-engine-{v}-{p}.zip"
SHA256 = {
    "linux-x64": "8d07392015c64a811e67cc098fc6fce2f599ee43b10db785df558eda29c1224d",
    "linux-arm64": "d7a953ff5c9fcd3438c4d201296f4b0902eae224f2ee02774d3f302c1d58c66c",
    "macos-universal": "e0a81a3640a50265fe113fd5cd8a25edfd9d33a6b110998c0288367a86c27634",
    "windows-x64": "934bb127617f65b5fae13cca2af7e9ef7c9aadf6d606ae371bdccf34a6a40cfa",
    "windows-arm64": "f3886001262fb4fd33caaea7f2a2df62a4e891d7a4929681dd1a2d9cc9210612",
    "android-arm64-v8a": "82a44b6c422d5b7074586683d706e45120b6a25dfa40441b6251f8b084ffa9fb",
    "android-armeabi-v7a": "f0a27fedebf452dbd0db3405c6f5ae33e0b7826b88dd0e6730ee9faf10ee275a",
    "android-x86_64": "0ca4ddcdae4e2fc7085700abd2dd0cd83d3347c7342ae79400192a00919a4866",
}


def library_name(plat):
    return "ballistic.dll" if plat.startswith("windows") else "libballistic.dylib" if plat.startswith("macos") \
        else "libballistic.so"


def platform_name(sysplat=None, machine=None, android=None):
    """The release's name for this machine, or None if there is none for it."""
    sysplat = sys.platform if sysplat is None else sysplat
    m = (platform.machine() if machine is None else machine).lower()
    if android is None:
        android = hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ
    arm64 = m in ("aarch64", "arm64", "armv8", "armv8b")
    x64 = m in ("x86_64", "amd64", "x64")
    if sysplat.startswith("win"):
        return "windows-arm64" if arm64 else "windows-x64" if x64 else None
    if sysplat == "darwin":
        return "macos-universal"
    if android:
        return ("android-arm64-v8a" if arm64 else "android-x86_64" if x64
                else "android-armeabi-v7a" if m.startswith("arm") else None)
    if sysplat.startswith("linux"):
        return "linux-arm64" if arm64 else "linux-x64" if x64 else None
    return None


def home(env=None):
    """Where installed libraries live: CLIo's folder in the user's data (next to the saves)."""
    env = os.environ if env is None else env
    if env.get("CLIO_DATA"):
        root = env["CLIO_DATA"]
    elif os.name == "nt":
        root = os.path.join(env.get("APPDATA") or os.path.expanduser("~"), "clio")
    else:
        root = os.path.join(env.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"), "clio")
    return os.path.join(root, "ballistic")


def installed(env=None, plat=None):
    """The library --get-ballistic put here, or None."""
    plat = plat or platform_name()
    if not plat:
        return None
    path = os.path.join(home(env), RELEASE, library_name(plat))
    return path if os.path.isfile(path) else None


def get(out=print, env=None, plat=None, opener=None):
    """Download, check and install. Returns 0 when the library is in place, 1 when not."""
    plat = plat or platform_name()
    if plat not in SHA256:
        out("Ballistic Engine %s has no library built for this machine (%s, %s). Build it from source "
            "(https://github.com/eigensoundlab/ballistic-engine) and set CLIO_BALLISTIC_LIB to it."
            % (RELEASE, sys.platform, platform.machine()))
        return 1
    url = URL.format(v=RELEASE, p=plat)
    out("Downloading Ballistic Engine %s for %s ..." % (RELEASE, plat))
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
    top = "ballistic-engine-%s-%s/" % (RELEASE, plat)
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
    try:
        from . import CEngine, ENGINE_COMMIT
        engine = CEngine(lib)
        if ENGINE_COMMIT not in engine.reference:
            out("It follows %s, not Ballistic %s as CLIo does: it will not be used." % (engine.reference, ENGINE_COMMIT))
            return 1
        out("It loads: %s %s. Ballistic sounds of the kinds it has ported now render in the game itself."
            % (engine.version, engine.reference))
    except OSError as e:
        out("It does not load on this machine: %s" % e)
        return 1
    return 0

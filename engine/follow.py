# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""``python -m engine.follow picture 0.10.0``: make CLIo follow a release of one of the libraries it can
download (``picture``, ``motion``).

It reads the release's ``checksums.txt``, downloads every zip listed for a machine CLIo knows, checks each against
that list and that the library is where ``--get-...`` will look for it, and then writes the release, the SHA-256
of each zip and its size into the library's ``fetch.py`` and ``engine/downloads.py``. Nothing is written unless
every zip is right. ``--check`` only says what would change. For those who look after CLIo; a game never runs it.

Where this Python cannot reach GitHub (a certificate it cannot check, no network), ``--from FOLDER`` takes the
release's files from a folder instead - its ``checksums.txt`` and zips as a browser saved them (a list saved as
``checksums (6).txt`` is found too). They are checked against each other in the same way.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARIES = {                                            # name: (its fetch module, its sizes in downloads.py)
    "picture": ("picture/fetch.py", "PICTURE_SIZE"),
    "motion": ("motion/fetch.py", "MOTION_SIZE"),
}
MACHINES = ("android-arm64-v8a", "android-armeabi-v7a", "android-x86_64", "linux-arm64", "linux-x64",
            "macos-universal", "windows-arm64", "windows-x64")


def _module(name):
    import importlib
    return importlib.import_module("engine." + LIBRARIES[name][0][:-3].replace("/", "."))


def _read(url, opener=None):
    with (opener or urllib.request.urlopen)(url, timeout=120) as r:
        return r.read()


def listed(text, stem):
    """{machine: sha256} from a checksums.txt, for the zips named ``<stem><machine>.zip``."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch("[0-9a-f]{64}", parts[0]):
            continue
        name = parts[1].lstrip("*").split("/")[-1]
        if name.startswith(stem) and name.endswith(".zip") and name[len(stem):-4] in MACHINES:
            out[name[len(stem):-4]] = parts[0]
    return out


def why(e):
    """One more line for an error of the network, where there is something to say: None otherwise."""
    text = str(e)
    if "CERTIFICATE_VERIFY_FAILED" in text:
        return ("This Python could not check GitHub's certificate - the release itself may be fine. A company proxy or "
                "an antivirus that reads HTTPS does this, and so does a Python without the system's certificates (one "
                "from MSYS2 or Git Bash's own, where cmd's or PowerShell's works).")
    if "404" in text:
        return "There is no such file: no such release, or one that has no files yet (made by hand before its workflow ran)."
    return None


def from_folder(folder):
    """An opener that takes a release's files from ``folder``: each by its name, and ``checksums.txt`` also from a
    list a browser saved under another name (``checksums (6).txt``) if that one lists the zips asked about."""
    def opened(url, timeout=None):
        name = url.rsplit("/", 1)[1]
        path = os.path.join(folder, name)
        if name == "checksums.txt" and not os.path.isfile(path):
            stem = opened.stem
            for other in sorted(os.listdir(folder), key=lambda n: -os.path.getmtime(os.path.join(folder, n))):
                if other.lower().startswith("checksums") and other.lower().endswith(".txt"):
                    with open(os.path.join(folder, other), "rb") as f:
                        data = f.read()
                    if stem and listed(data.decode("utf-8", "replace"), stem):
                        return io.BytesIO(data)
        if not os.path.isfile(path):
            raise OSError("%s is not in %s" % (name, folder))
        return open(path, "rb")
    opened.stem = None
    return opened


def gather(name, version, opener=None, out=print):
    """({machine: sha256}, {machine: bytes}) of a release, every zip downloaded and checked; None when it is not
    as it should be (and why is said)."""
    fetch = _module(name)
    url = fetch.URL.format(v=version, p="linux-x64")
    base, stem = url.rsplit("/", 1)[0], url.rsplit("/", 1)[1][:-len("linux-x64.zip")]
    if hasattr(opener, "stem"):
        opener.stem = stem                               # (a folder's opener: which list is this release's)
    try:
        sums = listed(_read(base + "/checksums.txt", opener).decode("utf-8", "replace"), stem)
    except Exception as e:
        out("Could not read %s/checksums.txt: %s" % (base, e))
        if why(e):
            out(why(e))
        if not hasattr(opener, "stem"):
            out("With the release's checksums.txt and zips saved to a folder by a browser: python -m engine.follow %s %s "
                "--from FOLDER" % (name, version))
        return None
    if not sums:
        out("%s/checksums.txt lists no %s<machine>.zip." % (base, stem))
        return None
    sizes = {}
    for plat in sorted(sums):
        try:
            data = _read(fetch.URL.format(v=version, p=plat), opener)
        except Exception as e:
            out("Could not get the zip for %s: %s" % (plat, e))
            return None
        if hashlib.sha256(data).hexdigest() != sums[plat]:
            out("The zip for %s does not match the release's own checksums.txt." % plat)
            return None
        want = "%s%s/lib/%s" % (stem, plat, fetch.library_name(plat))
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if want not in z.namelist():
                    out("The zip for %s has no %s." % (plat, want))
                    return None
        except zipfile.BadZipFile:
            out("The file for %s is not a zip." % plat)
            return None
        sizes[plat] = len(data)
        out("  %-20s %8d bytes  %s" % (plat, len(data), sums[plat]))
    return sums, sizes


def _table(text, name, body, note=""):
    """``text`` with the dict assigned to ``name`` given ``body`` (its lines) and ``note`` on its first line."""
    got = re.search(r"^%s = \{[^\n]*\n(?:[^}]*\n)?\}" % re.escape(name), text, re.M)
    if not got:
        raise ValueError("no %s = {...} to write to" % name)
    head = "%s = {" % name
    if note:
        head = head.ljust(32) + "# " + note
    return text[:got.start()] + "%s\n%s}" % (head, body) + text[got.end():]


def written(name, version, sums, sizes):
    """{path: new text} for the two files that say which release is followed."""
    fetch_path = os.path.join(HERE, LIBRARIES[name][0])
    down_path = os.path.join(HERE, "downloads.py")
    with open(fetch_path, encoding="utf-8") as f:
        text = f.read()
    text, n = re.subn(r'^RELEASE = "[^"]*"', 'RELEASE = "%s"' % version, text, count=1, flags=re.M)
    if n != 1:
        raise ValueError("no RELEASE in %s" % fetch_path)
    text = _table(text, "SHA256", "".join('    "%s": "%s",\n' % (p, sums[p]) for p in sorted(sums)),
                  "from the release's checksums.txt")
    with open(down_path, encoding="utf-8") as f:
        down = f.read()
    cells = ['"%s": %d' % (p, sizes[p]) for p in sorted(sizes)]
    lines, line = [], "   "
    for c in cells:
        if len(line) + len(c) + 2 > 116:
            lines.append(line.rstrip())
            line = "   "
        line += " " + c + ","
    lines.append(line.rstrip())
    down = _table(down, LIBRARIES[name][1], "\n".join(lines) + "\n")
    return {fetch_path: text, down_path: down}


def main(argv=None, opener=None, out=print):
    given = list(sys.argv[1:] if argv is None else argv)
    args = [a for a in given if a != "--check"]
    check = len(args) != len(given)
    folder = None
    if "--from" in args:
        k = args.index("--from")
        folder = args[k + 1] if k + 1 < len(args) else ""
        del args[k:k + 2]
    if (len(args) != 2 or args[0] not in LIBRARIES or not re.fullmatch(r"\d+\.\d+\.\d+", args[1])
            or (folder is not None and not os.path.isdir(folder))):
        if folder is not None and not os.path.isdir(folder):
            out("--from takes a folder that is there: %r is not." % folder)
        out("usage: python -m engine.follow %s VERSION [--check] [--from FOLDER]     (as in: motion 0.25.0)" % "|".join(LIBRARIES))
        return 2
    if folder is not None:
        opener = from_folder(folder)
    name, version = args
    out("%s %s:" % (name, version))
    got = gather(name, version, opener, out)
    if got is None:
        out("Nothing was changed.")
        return 1
    changed = []
    for path, text in written(name, version, *got).items():
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                continue
        changed.append(os.path.relpath(path, os.path.dirname(HERE)))
        if not check:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    if not changed:
        out("CLIo follows this release already.")
    else:
        out(("These would change: %s" if check else "Written: %s. Run the tests, then commit.") % ", ".join(changed))
    return 0 if not (check and changed) else 1


if __name__ == "__main__":
    sys.exit(main())

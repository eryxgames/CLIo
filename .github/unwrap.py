"""Join the wrapped lines of each paragraph and list item of a Markdown file onto one.

GitHub shows the line breaks of a release's notes as they are, so notes taken from
CHANGELOG.md (wrapped at 90 columns) would come out ragged.  Headings, blank lines,
tables and fenced code are left alone.

    python .github/unwrap.py notes.md
"""
import re
import sys


def unwrap(text):
    out, para, fenced = [], None, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            if para is not None:
                out.append(para)
                para = None
            fenced = not fenced
            out.append(line)
            continue
        if fenced:
            out.append(line)
            continue
        starts = not s or s.startswith(("#", "|", "- ", "* ", "> ")) or re.match(r"\d+\. ", s)
        if para is not None and not starts:
            para += " " + s
            continue
        if para is not None:
            out.append(para)
            para = None
        if not s or s.startswith(("#", "|")):
            out.append(line)
        else:
            para = line.rstrip()
    if para is not None:
        out.append(para)
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(unwrap(text))

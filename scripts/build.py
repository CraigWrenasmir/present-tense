#!/usr/bin/env python3
"""Copy the public site into _site/ for deployment. Standard library only."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"
FILES = ["index.html", "lineage.html", "threads.html", "threads.js", "style.css", "app.js", "favicon.svg", "CNAME", "manifest.webmanifest", "icon-180.png", "icon-192.png", "icon-512.png", "preview.png"]
DATA = ["news.json", "readings.json", "library.json", "world.json", "ledger.json", "source-config.json", "translations.json", "WORLD-SOURCE.md", "attention.json", "chronicle.json", "record.json"]


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data" / "editions").mkdir(parents=True)
    (OUT / "data" / "narratives").mkdir(parents=True)
    (OUT / "data" / "chronicle").mkdir(parents=True)
    (OUT / "data" / "attention").mkdir(parents=True)
    for name in FILES:
        if (ROOT / name).exists():
            shutil.copy(ROOT / name, OUT / name)
    for name in DATA:
        src = ROOT / "data" / name
        if src.exists():
            shutil.copy(src, OUT / "data" / name)
    for ed in (ROOT / "data" / "editions").glob("*.json"):
        shutil.copy(ed, OUT / "data" / "editions" / ed.name)
    for ed in (ROOT / "data" / "narratives").glob("*.json"):
        shutil.copy(ed, OUT / "data" / "narratives" / ed.name)
    for ed in (ROOT / "data" / "chronicle").glob("*.json"):
        shutil.copy(ed, OUT / "data" / "chronicle" / ed.name)
    for ed in (ROOT / "data" / "attention").glob("*.json"):
        shutil.copy(ed, OUT / "data" / "attention" / ed.name)
    (OUT / ".nojekyll").write_text("")
    print(f"built _site with {sum(1 for _ in OUT.rglob('*') if _.is_file())} files")


if __name__ == "__main__":
    main()

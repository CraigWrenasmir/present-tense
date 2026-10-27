#!/usr/bin/env python3
"""Copy the public site into _site/ for deployment. Standard library only."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"
FILES = ["index.html", "style.css", "app.js", "favicon.svg"]
DATA = ["news.json", "readings.json", "library.json", "world.json", "ledger.json", "source-config.json", "translations.json", "WORLD-SOURCE.md"]


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data" / "editions").mkdir(parents=True)
    for name in FILES:
        shutil.copy(ROOT / name, OUT / name)
    for name in DATA:
        src = ROOT / "data" / name
        if src.exists():
            shutil.copy(src, OUT / "data" / name)
    for ed in (ROOT / "data" / "editions").glob("*.json"):
        shutil.copy(ed, OUT / "data" / "editions" / ed.name)
    (OUT / ".nojekyll").write_text("")
    print(f"built _site with {sum(1 for _ in OUT.rglob('*') if _.is_file())} files")


if __name__ == "__main__":
    main()

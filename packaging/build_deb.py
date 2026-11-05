#!/usr/bin/python3
"""Build a dependency-based Debian package without system changes."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "build" / "bale-desktop"
APP = STAGE / "usr" / "share" / "bale-desktop"

def main():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    APP.mkdir(parents=True)
    shutil.copytree(ROOT / "bale_desktop", APP / "bale_desktop", ignore=shutil.ignore_patterns("__pycache__"))
    control = STAGE / "DEBIAN"
    control.mkdir()
    (control / "control").write_text("""Package: bale-desktop
Version: 0.2.6
Architecture: all
Maintainer: Bale Desktop contributors <noreply@example.invalid>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1
Recommends: gir1.2-ayatanaappindicator3-0.1
Section: net
Priority: optional
Description: Unofficial Bale Web desktop client with multiple accounts
 Isolated persistent profiles, background operation and desktop notifications.
""")
    binary = STAGE / "usr" / "bin" / "bale-desktop"
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\ncd /usr/share/bale-desktop\nexec /usr/bin/python3 -m bale_desktop.app "$@"\n')
    binary.chmod(0o755)
    desktop = STAGE / "usr" / "share" / "applications"
    desktop.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / "io.github.baledesktop.App.desktop", desktop)
    icons = STAGE / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"
    icons.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / "io.github.baledesktop.App.png", icons)
    docs = STAGE / "usr" / "share" / "doc" / "bale-desktop"
    docs.mkdir(parents=True)
    shutil.copy2(ROOT / "README.md", docs)
    shutil.copy2(ROOT / "packaging" / "copyright", docs / "copyright")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(STAGE), str(output / "bale-desktop_0.2.6_all.deb")], check=True)

if __name__ == "__main__":
    main()

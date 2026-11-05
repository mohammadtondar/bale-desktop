#!/usr/bin/python3
"""Build a small AppImage: the app's code on top of the system's GTK/WebKitGTK.

WebKitGTK is not bundled (it would add 150+ MB and its helper processes do not
relocate reliably), so the AppImage needs the same packages as the .deb:
python3-gi, GTK 3 and WebKitGTK 4.1. AppRun explains how to install them if
they are missing.

Usage: build_appimage.py [path/to/appimagetool]
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bale_desktop import __version__ as VERSION  # noqa: E402

APP_ID = 'io.github.baledesktop.App'
STAGE = ROOT / 'build' / 'AppDir'
TOOL_URL = 'https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage'
UPDATE_INFO = 'gh-releases-zsync|mohammadtondar|bale-desktop|latest|bale-desktop_*_x86_64.AppImage.zsync'

APPRUN = r'''#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
# Lets GTK find the bundled icon; the system's data dirs still follow.
export XDG_DATA_DIRS="$HERE/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
PY=/usr/bin/python3
[ -x "$PY" ] || PY="$(command -v python3)"
if ! "$PY" -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("WebKit2", "4.1"); from gi.repository import Gtk, WebKit2' 2>/dev/null; then
    if command -v apt >/dev/null 2>&1; then
        HINT="sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-ayatanaappindicator3-0.1"
    elif command -v dnf >/dev/null 2>&1; then
        HINT="sudo dnf install python3-gobject gtk3 webkit2gtk4.1 libayatana-appindicator-gtk3"
    elif command -v pacman >/dev/null 2>&1; then
        HINT="sudo pacman -S python-gobject gtk3 webkit2gtk-4.1 libayatana-appindicator"
    elif command -v zypper >/dev/null 2>&1; then
        HINT="sudo zypper install python3-gobject-Gdk typelib-1_0-WebKit2-4_1"
    else
        HINT="python3-gi, GTK 3, WebKitGTK 4.1"
    fi
    MSG="بله دسکتاپ به GTK 3 و WebKitGTK 4.1 نیاز دارد. با این دستور نصب کنید:

$HINT"
    echo "$MSG" >&2
    zenity --error --no-wrap --title "بله دسکتاپ" --text "$MSG" 2>/dev/null \
        || kdialog --title "بله دسکتاپ" --error "$MSG" 2>/dev/null \
        || notify-send "بله دسکتاپ" "$MSG" 2>/dev/null
    exit 1
fi
export PYTHONPATH="$HERE/usr/share/bale-desktop${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m bale_desktop.app "$@"
'''


def appimagetool(given):
    if given:
        return Path(given)
    tool = ROOT / 'build' / 'appimagetool-x86_64.AppImage'
    if not tool.exists():
        print('Downloading appimagetool…')
        urllib.request.urlretrieve(TOOL_URL, tool)
        tool.chmod(0o755)
    return tool


def main():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    app = STAGE / 'usr' / 'share' / 'bale-desktop'
    app.mkdir(parents=True)
    shutil.copytree(ROOT / 'bale_desktop', app / 'bale_desktop', ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('README.md', 'LICENSE'):
        shutil.copy2(ROOT / name, app / name)

    apprun = STAGE / 'AppRun'
    apprun.write_text(APPRUN)
    apprun.chmod(0o755)

    desktop = (ROOT / 'packaging' / (APP_ID + '.desktop')).read_text()
    desktop = desktop.replace('[Desktop Entry]\n', '[Desktop Entry]\nX-AppImage-Version=%s\n' % VERSION, 1)
    (STAGE / (APP_ID + '.desktop')).write_text(desktop)
    applications = STAGE / 'usr' / 'share' / 'applications'
    applications.mkdir(parents=True)
    (applications / (APP_ID + '.desktop')).write_text(desktop)

    icon_source = ROOT / 'packaging' / (APP_ID + '-256.png')   # 2048 px is too large for an AppImage icon
    icons = STAGE / 'usr' / 'share' / 'icons' / 'hicolor' / '256x256' / 'apps'
    icons.mkdir(parents=True)
    shutil.copy2(icon_source, icons / (APP_ID + '.png'))
    shutil.copy2(icon_source, STAGE / (APP_ID + '.png'))
    os.symlink(APP_ID + '.png', STAGE / '.DirIcon')

    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    target = output / ('bale-desktop_%s_x86_64.AppImage' % VERSION)
    env = dict(os.environ, ARCH='x86_64', APPIMAGE_EXTRACT_AND_RUN='1')
    subprocess.run([str(appimagetool(sys.argv[1] if len(sys.argv) > 1 else None)), '--no-appstream',
                    '-u', UPDATE_INFO, str(STAGE), str(target)], check=True, cwd=output, env=env)
    print('Built:', target)


if __name__ == '__main__':
    main()

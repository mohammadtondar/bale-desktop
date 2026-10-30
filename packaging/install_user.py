#!/usr/bin/python3
"""Install this client for the current desktop user, without administrator access."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP_ID = 'io.github.baledesktop.App'


def main():
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    destination = data / 'bale-desktop-app'
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'bale_desktop', destination / 'bale_desktop',
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'README.md', destination / 'README.md')
    shutil.copy2(ROOT / 'LICENSE', destination / 'LICENSE')
    binary = Path.home() / '.local/bin/bale-desktop'
    binary.parent.mkdir(parents=True, exist_ok=True)
    # A Python launcher safely handles spaces and shell metacharacters in paths.
    binary.write_text('#!/usr/bin/python3\nimport sys\nsys.path.insert(0, ' +
                      repr(str(destination)) + ')\nfrom bale_desktop.app import main\nraise SystemExit(main())\n')
    binary.chmod(0o755)
    icons = data / 'icons/hicolor/512x512/apps'
    icons.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'packaging' / (APP_ID + '.png'), icons)
    applications = data / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    # Desktop launchers do not inherit the shell's PATH.
    executable = str(binary).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    desktop = (ROOT / 'packaging' / (APP_ID + '.desktop')).read_text()
    desktop = desktop.replace('Exec=bale-desktop', 'Exec="' + executable + '"')
    launcher = applications / (APP_ID + '.desktop')
    launcher.write_text(desktop)
    subprocess.run(['desktop-file-validate', str(launcher)], check=True)
    subprocess.run(['update-desktop-database', str(applications)], check=True)
    subprocess.run(['gtk-update-icon-cache', '--force', '--ignore-theme-index', str(data / 'icons/hicolor')], check=True)
    print('Installed:', binary)
    print('Desktop launcher:', launcher)


if __name__ == '__main__':
    main()

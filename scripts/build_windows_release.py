"""Build a new release without touching any cashier installation or database."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_pos_release import load_values, write_defaults


def fresh_release_directory(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if path.parent != root.resolve() or not path.name.startswith("release_"):
        raise ValueError("Release output must be a new release_* directory in the project root")
    path.mkdir(exist_ok=False)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="release_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--skip-dependencies", action="store_true")
    args = parser.parse_args()
    values = load_values(ROOT)
    compiler = next((str(path) for path in (
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe",
        Path(os.getenv("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
    ) if path.is_file()), shutil.which("iscc.exe"))
    if not compiler:
        raise SystemExit("Install Inno Setup 6 before building the Windows installer")
    release = fresh_release_directory(ROOT, args.output)

    def run(*command):
        subprocess.run(command, cwd=ROOT, check=True)

    if not args.skip_dependencies:
        run(sys.executable, "-m", "pip", "install", "PyQt6", "pyinstaller", "certifi",
            "-r", str(ROOT / "requirements-web.txt"))
    write_defaults(ROOT / "build/pos_defaults.json", values)
    for spec in ("BroostPOS.spec", "BroostGuard.spec", "BroostWebServer.spec"):
        run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(release),
            "--workpath", str(ROOT / "build/windows-release"), spec)
    app = release / "BroostPOS"
    for filename in ("CashierSystemGuard.exe", "BroostWebServer.exe"):
        shutil.copy2(release / filename, app / filename)
    for filename in ("logo.ico", "logo.png", "facebook-qr.jpeg"):
        shutil.copy2(ROOT / filename, app / filename)
    run(sys.executable, "scripts/smoke_windows_release.py", "--app-dir", str(app))
    # Customer databases, .env and logs are intentionally never copied.
    run(compiler, f"/DReleaseSourceDir={app}", f"/O{release}", "/FBroostPOS_Update", "setup.iss")
    print(f"Installer ready: {release / 'BroostPOS_Update.exe'}")


if __name__ == "__main__":
    main()

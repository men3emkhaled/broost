"""Build the cloud-only cashier without packaging a local database or server."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_pos_release import load_values,write_defaults
from scripts.build_windows_release import fresh_release_directory


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='release_cloud_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    parser.add_argument('--skip-dependencies',action='store_true')
    args=parser.parse_args()
    release=fresh_release_directory(ROOT,args.output)
    def run(*args):subprocess.run(args,cwd=ROOT,check=True)
    if not args.skip_dependencies:
        run(sys.executable,'-m','pip','install','PyQt6','PyQt6-WebEngine','pywin32','pyinstaller','certifi','qrcode')
    values=load_values(ROOT)
    values.pop('operational_reset_id',None)
    values['mode']='cloud'
    write_defaults(ROOT/'build/pos_defaults.json',values)
    run(sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(release),'--workpath',str(ROOT/'build/cloud-release'),'BroostCloud.spec')
    app=release/'BroostPOS'
    shutil.copy2(ROOT/'logo.ico',app/'logo.ico')
    run(sys.executable,'scripts/smoke_cloud_release.py','--app-dir',str(app))
    compiler=Path(os.getenv('LOCALAPPDATA',''))/'Programs/Inno Setup 6/ISCC.exe'
    if not compiler.is_file():
        compiler=Path(os.getenv('ProgramFiles(x86)',''))/'Inno Setup 6/ISCC.exe'
    run(str(compiler),f'/DReleaseSourceDir={app}',f'/O{release}','setup_cloud.iss')
    print('Cloud installer ready:',release/'BroostPOS_Cloud_2.1.1_Advanced.exe')


if __name__=='__main__':main()

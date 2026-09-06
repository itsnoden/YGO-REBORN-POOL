"""Fetch reproducible, pinned upstream engine dependencies, never deck data."""
import argparse
import json
import subprocess
from pathlib import Path
from .import_pool import ROOT


def main():
    p=argparse.ArgumentParser();p.add_argument('--destination',default=str(ROOT/'vendor'));a=p.parse_args()
    dest=Path(a.destination);dest.mkdir(parents=True,exist_ok=True)
    for name,lock in json.loads((ROOT/'engine.lock.json').read_text()).items():
        target=dest/name
        existed=target.exists()
        if not existed:subprocess.run(['git','clone','--no-checkout',lock['url'],str(target)],check=True)
        if existed and subprocess.check_output(['git','-C',str(target),'status','--porcelain'],text=True).strip():
            raise RuntimeError(f'Refusing to overwrite modified dependency {target}')
        if subprocess.run(['git','-C',str(target),'cat-file','-e',lock['commit']],capture_output=True).returncode:
            subprocess.run(['git','-C',str(target),'fetch','origin',lock['commit']],check=True)
        subprocess.run(['git','-C',str(target),'checkout','--detach',lock['commit']],check=True)
        if name=='core':subprocess.run(['git','-C',str(target),'submodule','update','--init','--recursive'],check=True)


if __name__=='__main__':main()

"""Linux standalone build mirroring upstream premake source selections."""
import argparse
import concurrent.futures
import subprocess
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--core',required=True);p.add_argument('--output',required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args()
    core=Path(a.core).resolve();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
    excluded={'lbitlib.c','lcorolib.c','ldblib.c','linit.c','loadlib.c','loslib.c','ltests.c','lua.c','luac.c','lutf8lib.c','onelua.c'}
    lua=[p for p in (core/'lua/src').glob('*.c') if p.name not in excluded]
    if not lua:raise RuntimeError('Initialize pinned Lua submodule first')
    sources=sorted(core.glob('*.cpp'))+sorted((core/'RNG').glob('*.cpp'))+sorted(lua)
    def compile_one(src):
        obj=out/(src.name+'.o')
        cmd=['g++','-std=c++17','-O1','-fPIC','-fvisibility=hidden','-DOCGCORE_EXPORT_FUNCTIONS',
             '-I'+str(core/'lua/src'),'-I'+str(core/'lua'),'-I'+str(core),'-x','c++']
        if src in lua:cmd+=['-include',str(core/'lua/luaconf-customize.h')]
        result=subprocess.run(cmd+['-c',str(src),'-o',str(obj)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(f'{src.name}: {result.stderr}')
        print(src.name,flush=True);return str(obj)
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        objects=list(ex.map(compile_one,sources))
    subprocess.run(['g++','-shared','-Wl,--no-undefined','-o',str(out/'libocgcore.so')]+objects+['-ldl','-lm'],check=True)


if __name__=='__main__':main()

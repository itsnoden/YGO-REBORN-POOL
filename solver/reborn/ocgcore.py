"""Headless ctypes bridge for pinned ocgcore API 11.0.

Raw engine messages are privileged referee data. NEVER give this raw stream to
a learning policy: use observation.py + policy_view.py first.
"""
import ctypes as C
import json
import random
import sqlite3
import struct
from pathlib import Path
from .effects import UnsupportedInteraction
from .rules import get_profile

U8=C.c_uint8;U16=C.c_uint16;U32=C.c_uint32;U64=C.c_uint64;I32=C.c_int32;PTR=C.c_void_p
SCRIPT_OVERRIDE_DIR=Path(__file__).resolve().parents[1]/'script_overrides'


class CardData(C.Structure):
    _fields_=[('code',U32),('alias',U32),('setcodes',C.POINTER(U16)),('type',U32),('level',U32),
              ('attribute',U32),('race',U64),('attack',I32),('defense',I32),('lscale',U32),('rscale',U32),('link_marker',U32)]


class Player(C.Structure):_fields_=[('lp',U32),('draw',U32),('per_turn',U32)]


READ=C.CFUNCTYPE(None,PTR,U32,C.POINTER(CardData))
SCRIPT=C.CFUNCTYPE(C.c_int,PTR,PTR,C.c_char_p)
LOG=C.CFUNCTYPE(None,PTR,C.c_char_p,C.c_int)
DONE=C.CFUNCTYPE(None,PTR,C.POINTER(CardData))


class Options(C.Structure):
    _fields_=[('seed',U64*4),('flags',U64),('team1',Player),('team2',Player),
              ('reader',READ),('payload1',PTR),('scripts',SCRIPT),('payload2',PTR),
              ('log',LOG),('payload3',PTR),('done',DONE),('payload4',PTR),('unsafe',U8)]


class NewCard(C.Structure):
    _fields_=[('team',U8),('duelist',U8),('code',U32),('controller',U8),('location',U32),('sequence',U32),('position',U32)]


def split_messages(data):
    result=[];offset=0
    while offset<len(data):
        if offset+4>len(data):raise ValueError('Truncated message prefix')
        size=struct.unpack_from('<I',data,offset)[0];offset+=4
        if size<1 or offset+size>len(data):raise ValueError('Invalid message length')
        result.append(data[offset:offset+size]);offset+=size
    return result


def resolve_script_path(scripts,filename,overrides=SCRIPT_OVERRIDE_DIR):
    """Resolve an exact script name, preferring reviewed solver overrides."""
    scripts=Path(scripts)
    for source,path in (
        ('override',Path(overrides)/filename),
        ('root',scripts/filename),
        ('official',scripts/'official'/filename),
    ):
        if path.is_file():return source,path
    return None,None


class Duel:
    def __init__(self,library,database,scripts,seed=1,flags=None):
        self.lib=C.CDLL(str(Path(library).resolve()));self.scripts=Path(scripts).resolve()
        self.logs=[];self.errors=[];self.arrays=[];self.closed=False;self.handle=PTR()
        self.process_calls=0;self.loaded_scripts=[]
        self.lib.OCG_GetVersion.argtypes=[C.POINTER(C.c_int),C.POINTER(C.c_int)]
        major=C.c_int();minor=C.c_int();self.lib.OCG_GetVersion(C.byref(major),C.byref(minor))
        if (major.value,minor.value)!=(11,0):raise RuntimeError('Unsupported ocgcore ABI')
        self.lib.OCG_CreateDuel.argtypes=[C.POINTER(PTR),C.POINTER(Options)];self.lib.OCG_CreateDuel.restype=C.c_int
        self.lib.OCG_DestroyDuel.argtypes=[PTR]
        self.lib.OCG_DuelNewCard.argtypes=[PTR,C.POINTER(NewCard)]
        self.lib.OCG_StartDuel.argtypes=[PTR]
        self.lib.OCG_DuelProcess.argtypes=[PTR];self.lib.OCG_DuelProcess.restype=C.c_int
        self.lib.OCG_DuelGetMessage.argtypes=[PTR,C.POINTER(U32)];self.lib.OCG_DuelGetMessage.restype=PTR
        self.lib.OCG_LoadScript.argtypes=[PTR,C.c_char_p,U32,C.c_char_p];self.lib.OCG_LoadScript.restype=C.c_int
        self.lib.OCG_DuelSetResponse.argtypes=[PTR,PTR,U32]
        self.lib.OCG_DuelQueryCount.argtypes=[PTR,U8,U32];self.lib.OCG_DuelQueryCount.restype=U32
        con=sqlite3.connect(database);con.row_factory=sqlite3.Row
        self.data={r['id']:dict(r) for r in con.execute('SELECT * FROM datas')}
        try:self.names={r['id']:r['name'] for r in con.execute('SELECT id,name FROM texts')}
        except sqlite3.Error:self.names={}
        con.close()
        @READ
        def reader(payload,code,out):
            try:
                r=self.data.get(code)
                if r is None:self.errors.append(f'Missing engine data {code}');return
                codes=[];bits=r['setcode']
                bits &= (1<<64)-1
                while bits:codes.append(bits&0xffff);bits>>=16
                array=(U16*(len(codes)+1))(*codes,0);self.arrays.append(array)
                value=CardData(code,r['alias'],array,r['type'],r['level']&255,r['attribute'],r['race'],
                    r['atk'],r['def'],(r['level']>>24)&255,(r['level']>>16)&255,r['def'] if r['type']&0x4000000 else 0)
                C.memmove(out,C.byref(value),C.sizeof(value))
            except Exception as exc:self.errors.append(repr(exc))
        @SCRIPT
        def script_reader(payload,handle,name):
            try:
                filename=name.decode()
                if Path(filename).name!=filename:raise ValueError('Unexpected script path')
                source,path=resolve_script_path(self.scripts,filename)
                if path is None:return 0
                code=None
                stem=Path(filename).stem
                if stem.startswith('c') and stem[1:].isdigit():code=int(stem[1:])
                self.loaded_scripts.append({
                    'process_call':self.process_calls,
                    'filename':filename,
                    'source':source,
                    'code':code,
                    'name':self.names.get(code) if code is not None else None,
                })
                data=path.read_bytes()
                return self.lib.OCG_LoadScript(handle,data,len(data),name)
            except Exception as exc:self.errors.append(repr(exc));return 0
        @LOG
        def log(payload,message,kind):
            self.logs.append(dict(process_call=self.process_calls,kind=kind,message=message.decode(errors='replace')))
            if kind==0:self.errors.append(self.logs[-1]['message'])
        @DONE
        def done(payload,data):pass
        self.callbacks=(reader,script_reader,log,done)
        rng=random.Random(seed)
        profile=get_profile('reborn')
        if flags is None:flags=profile['flags']
        self.flags=flags
        self.profile_name='reborn'
        opts=Options((U64*4)(*[rng.getrandbits(64) for _ in range(4)]),flags,
                     Player(profile['starting_lp'],profile['opening_hand'],profile['draw_per_turn']),
                     Player(profile['starting_lp'],profile['opening_hand'],profile['draw_per_turn']),
                     reader,None,script_reader,None,log,None,done,None,0)
        status=self.lib.OCG_CreateDuel(C.byref(self.handle),C.byref(opts))
        if status!=0:raise RuntimeError(f'OCG_CreateDuel: {status}')
        for name in ('constant.lua','utility.lua'):
            if not script_reader(None,self.handle,name.encode()):raise RuntimeError(f'Failed loading {name}')
        self.check_errors()

    def check_errors(self):
        if self.errors:
            recent=[]
            for item in self.loaded_scripts[-20:]:
                label=item['filename']
                if item.get('source')=='override':label+=' [solver override]'
                if item.get('name'):label+=f" [{item['name']}]"
                recent.append(label)
            context='\nrecent loaded scripts: '+', '.join(recent) if recent else ''
            raise UnsupportedInteraction('\n'.join(self.errors)+context)

    def debug_snapshot(self):
        return {
            'process_calls':self.process_calls,
            'recent_logs':self.logs[-32:],
            'loaded_scripts':self.loaded_scripts[-128:],
        }

    def add(self,code,player,location=1,sequence=0):
        if code not in self.data:raise UnsupportedInteraction(f'Unknown passcode {code}')
        info=NewCard(player,0,code,player,location,sequence,8)
        self.lib.OCG_DuelNewCard(self.handle,C.byref(info));self.check_errors()

    def start(self):self.lib.OCG_StartDuel(self.handle);self.check_errors()

    def process(self):
        self.process_calls+=1
        status=self.lib.OCG_DuelProcess(self.handle);size=U32()
        ptr=self.lib.OCG_DuelGetMessage(self.handle,C.byref(size))
        messages=split_messages(C.string_at(ptr,size.value)) if size.value else []
        self.check_errors()
        if any(m[0]==1 for m in messages):raise UnsupportedInteraction('Core rejected response (MSG_RETRY)')
        return status,messages

    def respond(self,response):
        if isinstance(response,int):response=struct.pack('<i',response)
        buffer=C.create_string_buffer(response)
        self.lib.OCG_DuelSetResponse(self.handle,buffer,len(response))

    def count(self,player,zone):return self.lib.OCG_DuelQueryCount(self.handle,player,zone)

    def close(self):
        if self.handle and not self.closed:self.lib.OCG_DestroyDuel(self.handle);self.closed=True

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

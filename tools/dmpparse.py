import struct, sys

path = sys.argv[1]
with open(path, 'rb') as f:
    data = f.read()

assert data[:4] == b'MDMP', "not a minidump"
(sig, ver, nstreams, dir_rva, checksum, ts, flags) = struct.unpack_from('<IIIIIIQ', data, 0)

streams = {}
for i in range(nstreams):
    off = dir_rva + i*12
    (stype, dsize, rva) = struct.unpack_from('<III', data, off)
    streams[stype] = (dsize, rva)

def mdstring(rva):
    (length,) = struct.unpack_from('<I', data, rva)
    raw = data[rva+4:rva+4+length]
    return raw.decode('utf-16-le', errors='replace')

# Module list = 4
modules = []
if 4 in streams:
    dsize, rva = streams[4]
    (nmod,) = struct.unpack_from('<I', data, rva)
    p = rva + 4
    for i in range(nmod):
        base, size, csum, tds, name_rva = struct.unpack_from('<QIIII', data, p)
        name = mdstring(name_rva)
        modules.append((base, size, name))
        p += 108  # sizeof MINIDUMP_MODULE

# Exception stream = 6
exc_addr = None
exc_code = None
tid = None
if 6 in streams:
    dsize, rva = streams[6]
    tid, align = struct.unpack_from('<II', data, rva)
    ex = rva + 8
    (exc_code, exc_flags, exc_record, exc_addr, nparams, _al) = struct.unpack_from('<IIQQII', data, ex)
    params = struct.unpack_from('<15Q', data, ex+32)
    print(f"Exception thread id : {tid}")
    print(f"Exception code      : 0x{exc_code:08X}")
    print(f"Exception flags     : 0x{exc_flags:08X}")
    print(f"Exception address   : 0x{exc_addr:016X}")
    print(f"NumberParameters    : {nparams}")
    print(f"Params              : {[hex(x) for x in params[:nparams]]}")
else:
    print("No exception stream present")

def find_module(addr):
    for base, size, name in modules:
        if base <= addr < base+size:
            return base, size, name
    return None

print()
if exc_addr is not None:
    m = find_module(exc_addr)
    if m:
        base, size, name = m
        print(f"FAULTING MODULE: {name}")
        print(f"  base=0x{base:016X} size=0x{size:X}  offset=+0x{exc_addr-base:X}")
    else:
        print(f"Faulting address 0x{exc_addr:016X} not in any loaded module")

# System info stream = 7 (optional)
print()
print(f"Total modules loaded: {len(modules)}")
# Print modules of interest
import os
interesting = ('vrlink','galaxy','gxr','driver_','frame','hook','vrserver')
print("\n-- Modules of interest --")
for base, size, name in modules:
    bn = os.path.basename(name).lower()
    if any(k in bn for k in interesting):
        print(f"  0x{base:016X} +0x{size:08X}  {name}")

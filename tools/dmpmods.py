import struct, sys, os
data = open(sys.argv[1],'rb').read()
(sig, ver, nstreams, dir_rva) = struct.unpack_from('<IIII', data, 0)
streams={}
for i in range(nstreams):
    stype, dsize, rva = struct.unpack_from('<III', data, dir_rva+i*12)
    streams[stype]=(dsize,rva)
def mdstring(rva):
    (length,)=struct.unpack_from('<I',data,rva)
    return data[rva+4:rva+4+length].decode('utf-16-le','replace')
dsize,rva=streams[4]
(nmod,)=struct.unpack_from('<I',data,rva)
p=rva+4
mods=[]
for i in range(nmod):
    base,size,csum,tds,nrva=struct.unpack_from('<QIIII',data,p)
    mods.append((base,size,mdstring(nrva))); p+=108
mods.sort()
for base,size,name in mods:
    print(f"0x{base:012X} +0x{size:08X}  {name}")
print(f"\nTOTAL {len(mods)} modules")
# highlight non-system (not under windows/system32)
print("\n== Non-OS / third-party modules ==")
for base,size,name in mods:
    low=name.lower()
    if 'windows' in low or '\\system32' in low or 'winsxs' in low:
        continue
    print(f"  {name}")

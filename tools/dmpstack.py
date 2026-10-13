import struct, sys, os, bisect

data = open(sys.argv[1], 'rb').read()
(sig, ver, nstreams, dir_rva) = struct.unpack_from('<IIII', data, 0)
streams = {}
for i in range(nstreams):
    stype, dsize, rva = struct.unpack_from('<III', data, dir_rva + i*12)
    streams.setdefault(stype, []).append((dsize, rva))

def mdstring(rva):
    (length,) = struct.unpack_from('<I', data, rva)
    return data[rva+4:rva+4+length].decode('utf-16-le', 'replace')

# ---- modules
mods = []
dsize, rva = streams[4][0]
(nmod,) = struct.unpack_from('<I', data, rva)
p = rva + 4
for i in range(nmod):
    base, size, csum, tds, nrva = struct.unpack_from('<QIIII', data, p)
    mods.append((base, size, mdstring(nrva)))
    p += 108
mods.sort()
mod_bases = [m[0] for m in mods]

def find_mod(addr):
    i = bisect.bisect_right(mod_bases, addr) - 1
    if i >= 0:
        base, size, name = mods[i]
        if base <= addr < base + size:
            return mods[i]
    return None

# ---- memory ranges (Memory64List=9, MemoryList=5)
ranges = []  # (start, size, file_offset)
if 9 in streams:
    dsize, rva = streams[9][0]
    nr, base_rva = struct.unpack_from('<QQ', data, rva)
    p = rva + 16
    off = base_rva
    for i in range(nr):
        start, size = struct.unpack_from('<QQ', data, p)
        ranges.append((start, size, off))
        off += size
        p += 16
if 5 in streams:
    dsize, rva = streams[5][0]
    (nr,) = struct.unpack_from('<I', data, rva)
    p = rva + 4
    for i in range(nr):
        start, size, drva = struct.unpack_from('<QII', data, p)
        ranges.append((start, size, drva))
        p += 16
ranges.sort()
range_starts = [r[0] for r in ranges]

def read_mem(addr, n):
    i = bisect.bisect_right(range_starts, addr) - 1
    if i >= 0:
        start, size, off = ranges[i]
        if start <= addr < start + size:
            avail = min(n, start + size - addr)
            fo = off + (addr - start)
            return data[fo:fo+avail]
    return None

# ---- exception
dsize, rva = streams[6][0]
tid, _al = struct.unpack_from('<II', data, rva)
ex = rva + 8
(code, flags, rec, exaddr, nparams, _a) = struct.unpack_from('<IIQQII', data, ex)
ctx_size, ctx_rva = struct.unpack_from('<II', data, ex + 152)  # ThreadContext follows the 152-byte MINIDUMP_EXCEPTION

print(f"Exception 0x{code:08X} at 0x{exaddr:016X} thread {tid}")
m = find_mod(exaddr)
if m:
    print(f"  in {os.path.basename(m[2])}+0x{exaddr-m[0]:X}")

# ---- context from exception stream
ctx = data[ctx_rva:ctx_rva+ctx_size]
regs = {}
names = ['Rax','Rcx','Rdx','Rbx','Rsp','Rbp','Rsi','Rdi','R8','R9','R10','R11','R12','R13','R14','R15','Rip']
for i, nm in enumerate(names):
    regs[nm] = struct.unpack_from('<Q', ctx, 0x78 + i*8)[0]
print("\n-- Registers --")
for nm in names:
    v = regs[nm]
    mm = find_mod(v)
    tag = f"  -> {os.path.basename(mm[2])}+0x{v-mm[0]:X}" if mm else ""
    print(f"  {nm:4s} = 0x{v:016X}{tag}")

# ---- code bytes at RIP
rip = regs['Rip']
code_bytes = read_mem(rip - 16, 48)
print("\n-- Code around RIP (16 bytes before | at RIP) --")
if code_bytes:
    pre = code_bytes[:16]; post = code_bytes[16:]
    print("  before:", pre.hex(' '))
    print("  at RIP :", post.hex(' '))
    try:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        print("  disasm from RIP:")
        for ins in md.disasm(post, rip):
            print(f"    0x{ins.address:X}: {ins.mnemonic} {ins.op_str}")
            if ins.address - rip > 24: break
    except ImportError:
        print("  (capstone not available; raw bytes only)")
else:
    print("  (code memory not in dump)")

# ---- export resolution for system DLLs (on-disk PE parse)
export_cache = {}
def load_exports(path):
    if path in export_cache:
        return export_cache[path]
    res = []
    try:
        pe = open(path, 'rb').read()
        e_lfanew = struct.unpack_from('<I', pe, 0x3C)[0]
        nsec = struct.unpack_from('<H', pe, e_lfanew + 6)[0]
        opt_size = struct.unpack_from('<H', pe, e_lfanew + 20)[0]
        opt = e_lfanew + 24
        magic = struct.unpack_from('<H', pe, opt)[0]
        dd_off = opt + (0x70 if magic == 0x20B else 0x60)
        exp_rva, exp_size = struct.unpack_from('<II', pe, dd_off)
        secs = []
        sp = opt + opt_size
        for i in range(nsec):
            name = pe[sp:sp+8]
            vsize, vaddr, rsize, rptr = struct.unpack_from('<IIII', pe, sp + 8)
            secs.append((vaddr, vsize, rptr, rsize))
            sp += 40
        def rva2off(r):
            for vaddr, vsize, rptr, rsize in secs:
                if vaddr <= r < vaddr + max(vsize, rsize):
                    return rptr + (r - vaddr)
            return None
        if exp_rva:
            eo = rva2off(exp_rva)
            nfunc, nnames, afunc, anames, aords = struct.unpack_from('<IIIII', pe, eo + 0x14)
            fo = rva2off(afunc); no = rva2off(anames); oo = rva2off(aords)
            for i in range(nnames):
                nrva = struct.unpack_from('<I', pe, no + i*4)[0]
                ordv = struct.unpack_from('<H', pe, oo + i*2)[0]
                frva = struct.unpack_from('<I', pe, fo + ordv*4)[0]
                noff = rva2off(nrva)
                end = pe.index(b'\x00', noff)
                res.append((frva, pe[noff:end].decode('ascii', 'replace')))
        res.sort()
    except Exception as e:
        res = []
    export_cache[path] = res
    return res

def symbolize(addr):
    mm = find_mod(addr)
    if not mm:
        return None
    base, size, name = mm
    rva = addr - base
    exps = load_exports(name)
    if exps:
        rvas = [e[0] for e in exps]
        i = bisect.bisect_right(rvas, rva) - 1
        if i >= 0 and rva - rvas[i] < 0x20000:
            return f"{os.path.basename(name)}!{exps[i][1]}+0x{rva-rvas[i]:X}"
    return f"{os.path.basename(name)}+0x{rva:X}"

# ---- stack scan of faulting thread
dsize, rva = streams[3][0]
(nthr,) = struct.unpack_from('<I', data, rva)
p = rva + 4
stack_start = stack_size = stack_rva = None
for i in range(nthr):
    t_id, susp, pcls, prio, teb, s_start, s_size, s_rva, c_size, c_rva = struct.unpack_from('<IIIIQQIIII', data, p)
    if t_id == tid:
        stack_start, stack_size, stack_rva = s_start, s_size, s_rva
    p += 48

print(f"\n-- Stack scan (thread {tid}) --")
if stack_start is None:
    print("  thread not found in thread list")
else:
    rsp = regs['Rsp']
    print(f"  stack range 0x{stack_start:X}..0x{stack_start+stack_size:X}  RSP=0x{rsp:X}")
    stk = data[stack_rva:stack_rva+stack_size]
    off0 = max(0, rsp - stack_start)
    n = 0
    for off in range(off0 - (off0 % 8), stack_size - 8, 8):
        v = struct.unpack_from('<Q', stk, off)[0]
        mm = find_mod(v)
        if mm:
            # heuristic: return address if preceded by a call (E8 rel32 or FF /2 or 41 FF ..)
            pre = read_mem(v - 6, 6)
            is_ret = False
            if pre:
                if pre[1] == 0xE8 or pre[0] == 0xE8: is_ret = True
                if pre[4] == 0xFF and (pre[5] & 0x38) == 0x10: is_ret = True
                if pre[3] == 0xFF and (pre[4] & 0x38) == 0x10: is_ret = True
                if pre[2] == 0xFF and (pre[3] & 0x38) == 0x10: is_ret = True
                if pre[0] == 0xFF and (pre[1] & 0x38) == 0x10: is_ret = True
            flag = "RET" if is_ret else "   "
            print(f"  [rsp+0x{off-off0:05X}] {flag} 0x{v:016X}  {symbolize(v)}")
            n += 1
            if n > 60: break

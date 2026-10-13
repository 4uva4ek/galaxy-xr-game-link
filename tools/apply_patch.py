"""Apply CustomGameLink binary patches to the stock driver_SamsungVST.dll.

usage: apply_patch.py [--in vendor/SamsungVST/bin/win64/driver_SamsungVST.dll] [--out build/driver_SamsungVST.dll]

Refuses to run unless the input matches the stock hash and every patch site still holds
the expected original bytes, so a wrong or already-patched file is never touched.
"""
import argparse
import hashlib
import os
import sys

STOCK_SHA256 = "ed9f9f8d5f26b35fd564c5b474555cb0fcb2d636439dd7b52681a0c159a0cd42"

# (name, file offset, original bytes, patched bytes, rationale)
PATCHES = [
    (
        "0001-amf-init-check-factory",
        0xD6CDC6,
        bytes.fromhex("4883790800"),   # cmp qword ptr [rcx+0x08], 0   ; m_hLibrary
        bytes.fromhex("4883791000"),   # cmp qword ptr [rcx+0x10], 0   ; m_pFactory
        "AMFFactoryHelper::Init (+0xD6D9C0): treat the helper as initialised only when "
        "m_pFactory exists, not merely when amfrt64.dll was loaded. After a failed AMFInit "
        "the second Init() call used to return AMF_OK with a NULL factory, which "
        "VideoEncoderAMF::Initialize (+0xD5F9C0) dereferenced at +0xD5FA31.",
    ),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(root, "vendor", "SamsungVST", "bin", "win64", "driver_SamsungVST.dll"))
    ap.add_argument("--out", dest="dst", default=os.path.join(root, "build", "driver_SamsungVST.dll"))
    args = ap.parse_args()

    data = bytearray(open(args.src, "rb").read())
    actual = sha256(data)
    if actual != STOCK_SHA256:
        print(f"input is not the stock driver: sha256 {actual} != {STOCK_SHA256}")
        return 2

    for name, off, orig, new, why in PATCHES:
        cur = bytes(data[off:off + len(orig)])
        if cur != orig:
            print(f"{name}: unexpected bytes at 0x{off:X}: {cur.hex()} (want {orig.hex()})")
            return 3
        data[off:off + len(new)] = new
        print(f"{name}: 0x{off:X} {orig.hex()} -> {new.hex()}")

    os.makedirs(os.path.dirname(args.dst), exist_ok=True)
    open(args.dst, "wb").write(data)
    print(f"written {args.dst}")
    print(f"patched sha256 {sha256(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

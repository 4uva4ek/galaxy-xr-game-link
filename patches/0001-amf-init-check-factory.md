# 0001 — AMFFactoryHelper::Init: check the factory, not the library handle

**Target:** `driver_SamsungVST.dll` stock `ed9f9f8d…cd42` (build 2026-04-08)
**Site:** RVA `+0xD6D9C6`, file offset `0xD6CDC6`
**Change:** `48 83 79 08 00` → `48 83 79 10 00` (one byte, `cmp qword ptr [rcx+8],0` → `cmp qword ptr [rcx+0x10],0`)

## Bug

`AMFFactoryHelper::Init` (`+0xD6D9C0`, AMD's public helper compiled into the driver):

```
if (m_hLibrary != 0) { ++m_refCount; return AMF_OK; }     // "already initialised"
m_hLibrary = LoadLibrary(L"amfrt64.dll");                 // stored BEFORE validation
if (m_hLibrary && (AMFInit = GetProcAddress(...))) {
    res = AMFInit(AMF_FULL_VERSION, &m_pFactory);         // m_pFactory at +0x10
    if (res != AMF_OK) return res;                        // m_hLibrary stays set, m_pFactory NULL
    ...
}
return AMF_FAIL;
```

Object layout: `+0x08 m_hLibrary`, `+0x10 m_pFactory`, `+0x18 m_pDebug`, `+0x20 m_pTrace`, `+0x28 version`, `+0x30 refcount`.
`GetFactory()` (`+0xD6D9B0`) is `return m_pFactory`.

The driver calls `Init()` twice per encoder start:

1. `VideoEncoderAMF::GetCodecSupported` (`+0xD5F5C0`) — `Init()` fails when `amfrt64.dll` loads but
   `AMFInit` finds no AMD adapter (orphaned runtime shim on an NVIDIA box). The error is thrown as an
   `AMFException` and caught by `CEncoder`, which falls back to NVENC. Side effect: `m_hLibrary` is now set.
2. `VideoEncoderAMF::Initialize` (`+0xD5F9C0`) — `Init()` takes the early-return path, reports `AMF_OK`,
   `GetFactory()` returns NULL, and `factory->CreateContext` dereferences it at `+0xD5FA31`
   (`mov rcx,[rax]` with RAX = 0). vrserver dies; XRLinkApp tears the session down.

## Fix

Key the early return on `m_pFactory` instead of `m_hLibrary`. After a failed `AMFInit` the second call
re-enters the slow path, `LoadLibrary` returns the already-loaded module (reference count bump only),
`AMFInit` fails again, and `Initialize` throws cleanly like `GetCodecSupported` did. With a working AMD
runtime the first call sets `m_pFactory`, so later calls still take the fast path — behaviour unchanged.

Residual: the duplicate `LoadLibrary` reference is never released (`Terminate` frees once). Harmless.

## Verify

```
python tools/apply_patch.py           # refuses non-stock input, prints patched sha256
```
Host condition to exercise the fix: `C:\Windows\System32\amfrt64.dll` present, no AMD adapter present.
Expected in `driver_SamsungVST`'s log: "AMF Error … g_AMFFactory.Init()" twice, then NVENC initialises and
the session streams.

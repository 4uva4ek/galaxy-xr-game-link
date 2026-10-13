# Samsung Game Link: vrserver crash on every start — 2026-10-13

## Symptom
Starting a Game Link (Samsung XR Link) PCVR session closes immediately and SteamVR does not come up.
From the user's side: "Game Link falls over and does not launch SteamVR".

## Root cause (confirmed)
`driver_SamsungVST.dll` (Samsung's SteamVR driver, stock build 2026-04-08, ALVR-derived) crashes inside
`VideoEncoderAMF::Initialize` with a NULL-pointer dereference. The encoder selection tries the AMD AMF
encoder before NVENC ("Try to use VideoEncoderAMF" -> "Try to use VideoEncoderNVENC"); the AMF factory
loader (`amfrt64.dll` / `AMFInit` / `AMFQueryVersion`) returns NULL and the caller uses it without a check.

Why the factory is NULL on this PC:
- `C:\Windows\System32\amfrt64.dll` is present. It is the thin AMD AMF *shim* (147 KB, no version
  resource, imports only kernel32/advapi32/user32) that locates the real runtime (`amfrtdrv64.dll`,
  `amfrtlt64.dll`) through `D3DKMTEnumAdapters`/`D3DKMTQueryAdapterInfo` on a present AMD display adapter.
- The only AMD display adapter is the Ryzen 7 9800X3D integrated `AMD Radeon(TM) Graphics`. It is currently
  NOT present (`Get-PnpDevice`: present=False, installed 2026-06-05, last arrival 2026-08-15). The driver
  package `u0420529.inf_amd64_94ad5a6c4d1a04e2` is still in DriverStore, but with no AMD adapter the shim
  cannot resolve the runtime, so `AMFInit` yields no factory.
- Samsung's code dereferences that NULL -> access violation -> vrserver dies -> XRLinkApp sees the SteamVR
  process exit (`SteamVRProcessExitedEvent_Handler wireless disconnect`), sends DISCONNECT to the headset,
  unregisters its driver, and the headset app `com.samsung.android.xrlink` finishes (killed as cached,
  `cch+5 CEM` — not a native crash). SteamVR then restarts in safe mode with no HMD
  (`VR_Init error, exiting: Hmd Not Found (108)`), which is the "does not launch SteamVR" part.

## Evidence
- Crash dump `%LOCALAPPDATA%\CrashDumps\vrserver.exe.28584.dmp` (2026-10-13 15:47):
  - Exception 0xC0000005 (read of address 0), thread 33472, RIP = `driver_SamsungVST.dll+0xD5FA31`.
  - Instruction at RIP: `mov rcx,[rax]` with RAX = 0; preceding `call driver_SamsungVST+0xD6D9B4` then `mov rdi,rax`.
  - String refs around RIP: "Initialize Triggered", "g_AMFFactory.Init()",
    "g_AMFFactory.GetFactory()->CreateContext(&m_amfContext)", "m_amfContext->InitDX11(m_d3dRender->GetDevice())".
  - String refs in the callee `+0xD6D9B4`: "amfrt64.dll", "AMFInit", "AMFQueryVersion".
  - Caller frames `+0xD4771E/+0xD47A82/+0xD484AA`: "Try to use VideoEncoderAMF", "Try to use VideoEncoderNVENC",
    "All VideoEncoder are not available. VCE: %s, NVENC: %s", "Encoder resolution is width %d height %d".
  - Modules loaded at the crash include `C:\Windows\System32\amfrt64.dll` and `amdlvr64.dll`;
    `driver_GalaxyXRNative.dll` and `driver_vrlink.dll` were NOT loaded (Samsung's launcher takes exclusive
    `external_drivers` in openvrpaths while a session runs; the crash happens during SamsungVST's own Init).
  - Full outputs: `vrserver.exe.28584-stack.txt`, `vrserver.exe.28584-modules.txt` (tools in `tools/`).
- Samsung logs (`C:\ProgramData\SamsungVST\Log`): every StartStreaming since 2026-07-23 is followed within
  1-2 s by `SteamVRProcessExitedEvent_Handler wireless disconnect`. Sessions on 2026-05-06 and 2026-06-29
  streamed for minutes (no exit event). The 2026-04-08 (driver install day) attempts also failed.
- System32 AMD user-mode files (`amfrt64.dll`, `amdlvr64.dll`, `amdxc64.dll`, `atidxx64.dll`, ...) were
  created 2026-06-05 21:41 by the Radeon driver install (setupapi: `u0420529.inf`, `amdkmdag.sys`).
- `GPUType` reported by XRLinkService is "LOW GPU" in every session, working or not — not a factor.
- Virtual display adapters (Virtual Desktop, SudoMaker, Sunshine, Zako) were installed 2026-09-08..12 — after
  the regression; not a factor.
- `gxr_toolkit.appliedAt = 2026-07-23T00:15:21` in steamvr.vrsettings is 99 s before the first failing
  Game Link attempt. Coincidental: the toolkit edits only `driver_vrlink`/`vrlink_*`/`gxr_toolkit` keys that
  SamsungVST does not read, and the crash site is the AMF loader, not settings parsing.
- The SteamVR compositor error "Failed to LiquidVR::D3D11CreateDeviceHP3D (Error = 2)" is the same orphaned
  AMD runtime (`amdlvr64.dll`) being probed on an NVIDIA GPU; harmless for SteamVR itself.

## What was ruled out
- GalaxyXRNative / Companion code: not loaded in the crashing process.
- Wi-Fi/stream instability: the 15:32 Steam Link collapse (`HandleUnrecoverableError`, THROTTLE) is a
  separate incident; the Game Link crash is deterministic at encoder init, before any streaming.
- SteamVR interface-version mismatch: all driver-side interfaces SamsungVST requests
  (IVRServerDriverHost_006, IVRSettings_003, IVRDriverInput_003, IVRIPCResourceManagerClient_001, ...)
  are still exported by vrserver.exe 2.18.3.

## Fix options (none applied)
1. Make the orphaned shim unloadable so Samsung's AMF probe fails cleanly and falls back to NVENC:
   rename `C:\Windows\System32\amfrt64.dll` (admin; optionally `amdlvr64.dll` too). Reversible.
   A later AMD driver (re)install would restore it.
2. Enable the Ryzen integrated Radeon in BIOS so the shim finds its runtime (AMF init then fails cleanly on
   the NVIDIA D3D11 device). Adds a display adapter and may change DXGI adapter order.
3. Remove the AMD graphics driver remnants with AMD Cleanup Utility (removes shim + package).
4. Report to Samsung: `VideoEncoderAMF::Initialize` must check the AMF factory before use and the encoder
   selection should prefer NVENC on NVIDIA adapters.

## Reproduce the analysis
```
python tools/dmpparse.py <dump>    # exception + faulting module
python tools/dmpmods.py  <dump>    # full module list
python tools/dmpstack.py <dump>    # registers, bytes at RIP, stack scan with export symbolization
```

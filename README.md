# CustomGameLink

Modified Samsung Game Link (XR Link) PC driver for the Galaxy XR headset.

The stock package lives at `C:\ProgramData\SamsungVST` and is registered by `XRLinkApp` as a SteamVR
external driver (`SamsungVST`, `redirectsDisplay`, `alwaysActivate`) for the duration of a session.
`driver_SamsungVST.dll` is an ALVR-derived OpenVR driver; `XRLinkAudioSharing.dll` handles audio;
the headset side is `com.samsung.android.xrlink`.

## Layout

| Path | Purpose |
| --- | --- |
| `vendor/SamsungVST/` | Untouched stock package (driver build 2026-04-08, `server_version` 1.22). Never edit. |
| `vendor/SamsungVST.sha256` | Hashes of the stock files, to verify the vendor copy and to diff patched builds. |
| `notes/` | Reverse-engineering findings (offsets, strings, call paths). |
| `tools/` | Minidump parsers used for the crash analysis (`dmpparse.py`, `dmpmods.py`, `dmpstack.py`). |

## Known stock issues

- `VideoEncoderAMF::Initialize` dereferences a NULL AMF factory when `amfrt64.dll` loads but no AMD
  adapter is present (orphaned Radeon iGPU runtime). Crash site `driver_SamsungVST.dll+0xD5FA31`,
  loader `+0xD6D9B4`, encoder selection `+0xD47600..+0xD48600`. Details in
  `notes/amf-null-deref-crash.md`. Workaround on the host: rename `C:\Windows\System32\amfrt64.dll`.
  Proper fix for a patched build: check the factory, or try NVENC before AMF on NVIDIA adapters.

## Verify the vendor copy

```
cd vendor/SamsungVST && sha256sum -c ../SamsungVST.sha256
```

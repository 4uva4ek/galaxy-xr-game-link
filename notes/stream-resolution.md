# Stream resolution: what Game Link actually sends and where the limits are

Sources: decompiled `XRLinkApp.dll` (`SessionSettingUtil`, `OptimizeSettingUtil`, `SettingsViewModel`),
`C:\ProgramData\SamsungVST\XRLinkStreamSetting.json`, driver `FUN_180d47c50` (encoder resolution / FFR math),
headset `/vendor/etc/media_codecs*.xml`, XRLinkApp session log 2026-10-13 15:47.

## Pipeline

1. `XRLinkApp` writes `openvr_config` into `C:\ProgramData\SamsungVST\XRLinkCustomSettings.json`
   (`eye_resolution_*`, `refresh_rate`, `foveation_*`, `codec`, bitrate under `session_settings.video`).
2. `driver_SamsungVST.dll` reads that session file (ALVR style; strings `session.json` / `openvr_config`),
   renders at `eye_resolution`, then **foveated encoding** shrinks the frame before NVENC.
3. Headset decodes the shrunk frame and re-expands it on the panel (3552x3840 per eye, 90/72/60 Hz).

## Resolution tiers (`SessionSettingUtil.InitResolutionSizePair`, factor 116/135, width rounded up to 32)

| ResolutionType | enum | per eye | both eyes |
| --- | --- | --- | --- |
| High | 0 | 1920x2208 | 3840x2208 |
| VeryHigh | 1 | 2496x2880 | 4992x2880 |
| UltraHigh | 2 | 2976x3440 | 5952x3440 |
| Maximum | 3 | 3328x3840 | 6656x3840 |
| Low | 9 | 540x540 | phones only |

All tiers are selectable in the GUI in manual mode (`SettingType.UserSetting = 0`). In automatic mode
(`SettingType.Automatic = 1`) the tier comes from `XRLinkStreamSetting.json -> Resolution_Type[GPU]` and
Samsung caps **every** listed GPU at VeryHigh (bitrate 70-80 Mbit/s). RTX 5090 is not in that list, so it is
classified `LOW GPU` -> `High`; irrelevant in manual mode, but worth a JSON fix for automatic users.

## Foveated encoding (what makes it blurry)

`openvr_config.foveation_*` -> driver `FUN_180d47c50` ("GetEncResolution"): per axis
`pad = ceil(n*(1-center)/(2*edge))*2*edge`, `c = 1 - pad/n`, `encoded = ((1-c)/edge + c) * n`.
Samsung DK3 profile for every tier: center 0.7x0.6, shift 0.4x0.1, edge 4x4 -> everything outside the central
70%x60% is encoded at 1/4 resolution. Encoded frame sizes:

| tier | Samsung FFR (0.7x0.6, edge 4) | softer FFR (0.85x0.8, edge 2) | no FFR |
| --- | --- | --- | --- |
| VeryHigh | 3862x2015, 7.8 Mpix, 0.70 Gpix/s @90 | 4616x2592, 12.0 Mpix, 1.08 @90 | 4992x2880, 14.4 Mpix, 1.29 @90 |
| UltraHigh | 4608x2408, 11.1 Mpix, 1.00 @90 / 0.80 @72 | 5504x3096, 17.0 Mpix, 1.53 @90 | 5952x3440, 20.5 Mpix, 1.84 @90 |
| Maximum | 5156x2688, 13.9 Mpix, 1.25 @90 / 1.00 @72 | 6156x3456, 21.3 Mpix | 6656x3840, 25.6 Mpix, 2.30 @90 |

## Headset decoder budget

`c2.qti.hevc.decoder` declares performance points 3840x2160@60 (0.50 Gpix/s), 4096x2304@30, bitrate
1-100 Mbit/s. These are conservative: VeryHigh at 90 Hz (0.70 Gpix/s, 150 Mbit/s) already runs. The real
ceiling is unknown and must be found empirically; expect somewhere around 1.0-1.3 Gpix/s.

## Session on 2026-10-13 15:47 (user's current settings)

Manual mode, 90 Hz, 150 Mbit/s HEVC CBR, VeryHigh (4992x2880), FFR on with Samsung values, sharpening 1.0.
Effective: 0.70x panel resolution in the centre, 0.18x in the periphery, ~0.21 bit/pixel.

## Levers, cheapest first (all are JSON/GUI, no binary patch)

1. Tier UltraHigh or Maximum (GUI: Settings -> Resolution), keep HEVC.
2. Bitrate 150 -> 250-400 Mbit/s (`XRLinkSettings.json: BitRate`; GUI slider may cap lower).
3. FFR: larger centre, lower edge ratio (`Foveated_Rendering.Custom` in `XRLinkSettings.json`), or off.
4. 72 Hz buys 20% decoder budget for resolution.
5. Sharpening 1.0 -> 1.25-1.5 (`ColorCorrectionParams.sharpening`).

Test order within the decoder budget: UltraHigh@90 Samsung FFR (1.0 Gpix/s) -> Maximum@72 (1.0) ->
Maximum@90 (1.25) -> then relax FFR. Watch the headset logcat for decoder errors / dropped frames and the
XRLinkApp log line `SettingsViewModel::SessionSettingEventHandler ... ResolutionType:WxH` for what applied.

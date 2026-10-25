# VIDAA local control — protocol notes

Reverse-engineered notes for controlling a Hisense VIDAA TV locally. Device-specific values below are
placeholders (`<TV_IP>`, `AA:BB:CC:DD:EE:FF`) — fill in your own.

## Transport

- **MQTT v3.1.1 over TLS**, TV port **36669**.
- **Mutual TLS**: the TV presents a self-signed cert chained to `CN=RemoteCA`; the client must present a
  cert the TV's broker authorizes. Verify the server cert? No — `cert_reqs=CERT_NONE`, `tls_insecure`.
- Newer firmware (2024+) validates the **client cert identity**: it must be `CN=VidaaAppAndroidV01`
  (OU=multimedia, O=hh), valid 2024–2034. The older 2018 `CN=remoteclientmobile` cert still completes the
  TLS handshake but the broker returns **CONNACK rc 5 "Not authorized"**. That rc5 is the #1 gotcha.

## Authentication (dynamic)

Modern firmware derives the MQTT username/password from a timestamp. Use the **TV's own clock** (clock skew
breaks it) — read it from the UPnP HTTP `Date` header:

```
GET http://<TV_IP>:18400/MediaServer/rendererdevicedesc.xml   ->  Date: <RFC1123>
```

Then (constants are protocol-wide, not device-specific):

```
PATTERN = "38D65DC30F45109A369A86FCE866A85B"
XOR     = 6239759785777146216
MODERN_SALT   = "h!i@s#$v%i^d&a*a"
STANDARD_SALT = "h*i&s%e!r^v0i1c9"

client_id = f"{MAC}$his${md5(f'{PATTERN}${MAC}')[:6].upper()}_vidaacommon_001"
# modern:
username  = f"his${ts ^ XOR}"
digitsum  = sum(int(c) for c in str(ts)) % 10
password  = md5(f"{ts}${ md5(f'his{digitsum}{MODERN_SALT}')[:6].upper() }").upper()
```

Profiles: **modern** (salt=MODERN, user XORed), **middle** (salt=STANDARD, user XORed),
**remotenow** (salt=STANDARD, user=`his$<ts>`), **legacy** (static `hisenseservice/multimqttservice`).
Try modern→middle→remotenow. `MAC` is just a stable client identifier — a random MAC-shaped string works;
it does **not** need to match the TV.

## Pairing (one-time)

1. Connect (rc 0). Subscribe to the **exact** reply topics (this firmware denies wildcard `#` subscriptions — SUBACK 128).
2. Publish `.../ui_service/<cid>/actions/vidaa_app_connect` → TV shows a 4-digit PIN; an empty push arrives on
   `.../mobile/<cid>/ui_service/data/authentication`.
3. Publish the PIN: `.../ui_service/<cid>/actions/authenticationcode` = `{"authNum": <pin>}`.
   Success = `{"result":1,...}` (wrong/expired = `{"result":100,"info":"illegal authNum!!"}`).
4. Publish `.../platform_service/<cid>/data/gettoken` = `{"refreshtoken":""}` → token pair arrives on
   `.../mobile/<cid>/platform_service/data/tokenissuance` (access ~2d, refresh ~30d).

## Topic structure

```
/remoteapp/tv/ui_service/<cid>/actions/<action>          # you -> TV (UI ops)
/remoteapp/tv/remote_service/<cid>/actions/sendkey       # you -> TV (key)
/remoteapp/tv/platform_service/<cid>/...                 # you -> TV (tokens/settings)
/remoteapp/mobile/<cid>/<service>/data/<leaf>            # TV -> you (replies)
/remoteapp/mobile/broadcast/<service>/...                # TV -> everyone (events)
```

## Command surface (observed)

**Request (publish, mostly to `ui_service/.../actions/`)**
`sendkey`, `launchapp`, `changesource`, `changevolume`, `gettvstate`, `getvolume`, `sourcelist`,
`applist`, `getdeviceinfo`, `gettvinfo`, `capability`, `vidaa_app_connect`, `tvsleep`,
`authenticationcode`, `txtinputdata`, `bwsinputdata`. (`showmessage`/`toast` exist but were no-ops on
the tested firmware.)

**Reply / push leaves** (`.../data/<leaf>`): `state`, `gettvstate`, `getvolume`/`volume`, `sourcelist`,
`applist`, `getdeviceinfo`, `gettvinfo`, `capability`, `picturesetting`, `soundsetting`,
`hotelmodechange`, `authentication`, `tokenissuance`.

Notes:
- `picturesetting`/`soundsetting` are **push-only** — the TV broadcasts them when the user changes a
  setting in the menu; an empty query does not fetch them.
- `is_support_mouse:1` in `gettvinfo` indicates a pointer/cursor action exists, but its topic is not in any
  public integration (buried in the app's packed native lib — not statically recoverable).
- `screen_capture_supported:0` — no remote screenshot.

### launchapp = run your own web app

Most VIDAA apps are HTML5 web apps (`storeType:99`, `url` = an https page). `launchapp` with your own URL
navigates the TV's browser engine to it, full-screen:

```json
{"appId":"","name":"app","url":"http://<your-ip>:<port>/","urlType":37,"appName":"app","appUrl":"http://<your-ip>:<port>/","storeType":99}
```

## Other open services (no auth)

- **AirPlay** `:7000` — receiver; `GET /info` returns a device-info plist.
- **DLNA/UPnP** `:18400` (and `:38400`) — `RenderingControl` + `AVTransport` SOAP: cast a media URL,
  read volume/transport state. Live `SetVolume`/`SetMute` are often no-ops on live TV (apply during a cast).
- **Netflix NRDP** `:9080` — status endpoint.

## Gotchas

- rc 5 after a good TLS handshake → wrong/old **client cert** (need `VidaaAppAndroidV01`), not a password issue.
- rc 4/5 can also be **clock skew** — always derive creds from the TV's `Date` header.
- Wildcard (`#`) subscriptions are denied; subscribe to exact leaves.

# vidaa-toolkit

Local control for **Hisense VIDAA smart TVs** over their MQTT bus (port `36669`, mutual TLS) — no cloud, no account, fully on your LAN. Send keys, launch apps, **run your own web apps full-screen on the TV**, read live state, and map the firmware's command surface.

> Reverse-engineered for interoperability with a TV you own. Unofficial; not affiliated with or endorsed by Hisense/VIDAA. Topics and auth are undocumented and may change with firmware updates.

## What it does

- 🎮 **send any remote key** (`KEY_POWER`, `KEY_VOLUMEUP`, `KEY_HOME`, `KEY_NETFLIX`, …)
- 🚀 **`launchapp` with an arbitrary URL** — most VIDAA "apps" are just web pages, so you can run your **own** web app full-screen on the TV
- 🔌 **switch inputs** (TV / HDMI1-3 / AV)
- 👁️ **read live state** — what app/screen is active, right now
- 🧭 **dump device/firmware info**, app list, source list, capability flags
- 📡 **listen** to the TV's event bus (state, picture/sound settings pushed on change)

## Requirements

- Python 3.9+, `pip install -r requirements.txt`
- The TV on the same LAN
- A **VIDAA client certificate** (see below) — not shipped here

## Obtaining the client certificate

Newer VIDAA firmware requires mutual TLS with a client cert whose identity the TV validates
(`CN=VidaaAppAndroidV01` on 2024+ builds). This cert/key are the property of their owner and are
**not distributed** with this project. Extract them from the official **VIDAA Smart TV** Android app,
which you have a right to use for interoperability with your own TV:

```bash
# unzip the app's APK/App Bundle and find the keystore (name varies by build):
unzip -l app.apk | grep -iE '\.p12'
#   e.g. res/3R.p12  or  res/raw/client_mobile_android.p12

# export to PEM (OpenSSL 3.x needs -legacy):
openssl pkcs12 -legacy -in client_mobile_android.p12 -clcerts -nokeys -out vidaa_cert.pem -passin pass:<P12_PASSWORD>
openssl pkcs12 -legacy -in client_mobile_android.p12 -nocerts -nodes  -out vidaa_key.pem  -passin pass:<P12_PASSWORD>
```

Older TVs accept the legacy `hisenseservice/multimqttservice` login (`VIDAA_PROFILE=legacy`) and the
2018 `remoteclientmobile` cert; newer TVs reject both. See [PROTOCOL.md](PROTOCOL.md).

## Configure

```bash
cp config.example.env config.env
# edit config.env: set VIDAA_TV_IP, cert paths
set -a; source config.env; set +a
```

## Use

```bash
python3 pair.py                       # one-time: pair (enter the PIN the TV shows)
python3 vidaa.py state                # what's on the TV now
python3 vidaa.py info                 # device/firmware/apps/sources
python3 vidaa.py key KEY_VOLUMEUP KEY_VOLUMEDOWN
python3 vidaa.py source HDMI1
python3 vidaa.py launch http://<your-laptop-ip>:8099/   # your web app on the TV
python3 vidaa.py listen -s 90         # watch the TV's event bus
```

Example — run your own page on the TV:

```bash
cd webapp && python3 -m http.server 8099 --bind 0.0.0.0 &
python3 ../vidaa.py launch http://<your-laptop-ip>:8099/
```

## How it works

mTLS connect to `:36669`, then a timestamp-derived MQTT username/password (the TV's own clock,
read from its UPnP `Date` header, seeds the hash). First run shows a PIN on the TV; entering it
returns a long-lived token. Full write-up: **[PROTOCOL.md](PROTOCOL.md)**.

## Credits / prior art

Auth scheme and topic names build on community work: `stevene1919/hisense_vidaa`,
`warrenrees/pyvidaa`, `d3nd3/Hisense-mqtt-keyfiles`, and the original `mqtt-hisensetv`.

## License

MIT (code only). The VIDAA client certificate is **not** covered and is not included.

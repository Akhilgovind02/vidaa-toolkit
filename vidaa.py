#!/usr/bin/env python3
"""
vidaa.py — local control library + CLI for Hisense VIDAA TVs over MQTT (port 36669, mutual TLS).

Config via environment (or a .env you source — see config.example.env):
    VIDAA_TV_IP     TV IP address            (required)
    VIDAA_TV_MAC    a MAC-shaped client id    (default: random; any stable value works)
    VIDAA_CERT      client cert PEM path      (default: ./vidaa_cert.pem)
    VIDAA_KEY       client key PEM path       (default: ./vidaa_key.pem)
    VIDAA_PROFILE   auth profile              (default: modern; modern|middle|remotenow|legacy)

The client certificate/key are NOT shipped (they are the property of their owner).
See README.md -> "Obtaining the client certificate".
"""
from __future__ import annotations
import argparse, email.utils, hashlib, json, os, random, ssl, sys, time, urllib.request
import paho.mqtt.client as mqtt

# --- protocol constants (public; not device-specific) ---
MODERN_SALT = "h!i@s#$v%i^d&a*a"
STANDARD_SALT = "h*i&s%e!r^v0i1c9"
CLIENT_ID_PATTERN = "38D65DC30F45109A369A86FCE866A85B"
XOR_TIMESTAMP_MASK = 6239759785777146216
UPNP_PORTS = (18400, 38400)
PORT = 36669


def env(k, d=None): return os.environ.get(k, d)


def random_mac() -> str:
    return ":".join(f"{random.randint(0,255):02x}" for _ in range(6))


def tv_timestamp(ip: str, timeout: float = 3.0) -> int:
    """Read the TV's clock from its UPnP HTTP Date header (needed for dynamic auth)."""
    for p in UPNP_PORTS:
        try:
            url = f"http://{ip}:{p}/MediaServer/rendererdevicedesc.xml"
            with urllib.request.urlopen(url, timeout=timeout) as r:
                d = r.headers.get("Date")
                if d:
                    return int(email.utils.parsedate_to_datetime(d).timestamp())
        except Exception:
            pass
    return int(time.time())


def derive_credentials(mac: str, timestamp: int, profile: str = "modern"):
    """Return (client_id, username, password) for a VIDAA MQTT connect."""
    digest = hashlib.md5(f"{CLIENT_ID_PATTERN}${mac}".encode()).hexdigest().upper()
    client_id = f"{mac}$his${digest[:6]}_vidaacommon_001"
    if profile == "legacy":
        return client_id, "hisenseservice", "multimqttservice"
    if profile == "modern":
        salt, user = MODERN_SALT, f"his${timestamp ^ XOR_TIMESTAMP_MASK}"
    elif profile == "middle":
        salt, user = STANDARD_SALT, f"his${timestamp ^ XOR_TIMESTAMP_MASK}"
    else:  # remotenow / standard
        salt, user = STANDARD_SALT, f"his${timestamp}"
    digitsum = sum(int(c) for c in str(timestamp) if c.isdigit()) % 10
    salt_hash = hashlib.md5(f"his{digitsum}{salt}".encode()).hexdigest().upper()
    password = hashlib.md5(f"{timestamp}${salt_hash[:6]}".encode()).hexdigest().upper()
    return client_id, user, password


class Tv:
    def __init__(self, ip=None, mac=None, cert=None, key=None, profile=None):
        self.ip = ip or env("VIDAA_TV_IP")
        if not self.ip:
            sys.exit("set VIDAA_TV_IP (the TV's IP address)")
        self.mac = mac or env("VIDAA_TV_MAC") or random_mac()
        self.cert = cert or env("VIDAA_CERT", "vidaa_cert.pem")
        self.key = key or env("VIDAA_KEY", "vidaa_key.pem")
        self.profile = profile or env("VIDAA_PROFILE", "modern")
        ts = tv_timestamp(self.ip)
        self.cid, self.user, self.pw = derive_credentials(self.mac, ts, self.profile)
        self.ui = f"/remoteapp/tv/ui_service/{self.cid}/"
        self.remote = f"/remoteapp/tv/remote_service/{self.cid}/"
        self.platform = f"/remoteapp/tv/platform_service/{self.cid}/"
        self.mobile = f"/remoteapp/mobile/{self.cid}/"
        self._msgs = []

    def _client(self):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.cid,
                        clean_session=True, protocol=mqtt.MQTTv311)
        if not (os.path.isfile(self.cert) and os.path.isfile(self.key)):
            sys.exit(f"client cert/key missing ({self.cert}, {self.key}). See README 'Obtaining the client certificate'.")
        c.tls_set(ca_certs=None, certfile=self.cert, keyfile=self.key,
                  cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS)
        c.tls_insecure_set(True)
        c.username_pw_set(self.user, self.pw)
        return c

    def _run(self, on_connect, duration=4.0):
        c = self._client()
        c.on_connect = on_connect
        c.on_message = lambda cl, u, m: self._msgs.append((m.topic, m.payload.decode("utf-8", "replace")))
        c.connect(self.ip, PORT, 20)
        c.loop_start()
        time.sleep(duration)
        c.loop_stop(); c.disconnect()

    # --- high level ops ---
    def send_key(self, *keys):
        def oc(cl, u, f, r, pr=None): [cl.publish(self.remote + "actions/sendkey", k) or time.sleep(0.4) for k in keys]
        self._run(oc, 1.0 + 0.5 * len(keys))

    def launch_url(self, url):
        payload = json.dumps({"appId": "", "name": "app", "url": url, "urlType": 37, "appName": "app", "appUrl": url, "storeType": 99})
        self._run(lambda cl, u, f, r, pr=None: cl.publish(self.ui + "actions/launchapp", payload), 3.0)

    def change_source(self, source_id, name=None):
        payload = json.dumps({"sourceid": source_id, "sourcename": name or source_id})
        self._run(lambda cl, u, f, r, pr=None: cl.publish(self.ui + "actions/changesource", payload), 2.0)

    def _query(self, actions, leaves, duration=4.0):
        def oc(cl, u, f, r, pr=None):
            if getattr(r, "value", r) == 0:
                subs = [(f"{self.mobile}{svc}/data/{l}", 0) for svc in ("ui_service", "platform_service") for l in leaves]
                subs.append(("/remoteapp/mobile/broadcast/ui_service/state", 0))
                for i in range(0, len(subs), 20):
                    cl.subscribe(subs[i:i + 20])
                time.sleep(0.3)
                cl.publish(self.ui + "actions/vidaa_app_connect", '{"app_version":2,"connect_result":0,"device_type":"Mobile App"}')
                for a in actions:
                    cl.publish(self.ui + f"actions/{a}", ""); time.sleep(0.4)
        self._msgs = []
        self._run(oc, duration)
        return self._msgs

    def state(self):
        for t, p in self._query(["gettvstate"], ["state", "gettvstate"]):
            if "statetype" in p:
                return p
        return None

    def info(self):
        out = {}
        for t, p in self._query(["getdeviceinfo", "gettvinfo", "capability", "applist", "sourcelist"],
                                ["getdeviceinfo", "gettvinfo", "capability", "applist", "sourcelist"], 6.0):
            out[t.split("/data/")[-1]] = p
        return out

    def listen(self, seconds=60):
        def oc(cl, u, f, r, pr=None):
            if getattr(r, "value", r) == 0:
                leaves = ["ui_service/state", "ui_service/data/state", "ui_service/data/getvolume",
                          "platform_service/data/picturesetting", "platform_service/data/soundsetting"]
                subs = [(b + l, 0) for b in (self.mobile, "/remoteapp/mobile/broadcast/") for l in leaves]
                for i in range(0, len(subs), 20):
                    cl.subscribe(subs[i:i + 20])
                print("[listening — interact with the TV]", flush=True)
        c = self._client()
        c.on_connect = oc
        c.on_message = lambda cl, u, m: print(f"{m.topic.split('/',6)[-1]}  {m.payload.decode('utf-8','replace')[:400]}", flush=True)
        c.connect(self.ip, PORT, 20); c.loop_start(); time.sleep(seconds); c.loop_stop(); c.disconnect()


def main():
    ap = argparse.ArgumentParser(description="Local control for Hisense VIDAA TVs (MQTT/mTLS).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("state", help="print what's on the TV now")
    sub.add_parser("info", help="dump device/firmware info + apps + sources")
    k = sub.add_parser("key", help="send remote key(s), e.g. KEY_VOLUMEUP"); k.add_argument("keys", nargs="+")
    lu = sub.add_parser("launch", help="launch a URL full-screen on the TV"); lu.add_argument("url")
    sc = sub.add_parser("source", help="switch input (TV/HDMI1/HDMI2/HDMI3/AVS)"); sc.add_argument("source_id")
    ls = sub.add_parser("listen", help="live-log what the TV pushes"); ls.add_argument("-s", "--seconds", type=int, default=60)
    a = ap.parse_args()
    tv = Tv()
    if a.cmd == "state": print(tv.state())
    elif a.cmd == "info": print(json.dumps(tv.info(), indent=2))
    elif a.cmd == "key": tv.send_key(*a.keys); print("sent:", *a.keys)
    elif a.cmd == "launch": tv.launch_url(a.url); print("launched:", a.url)
    elif a.cmd == "source": tv.change_source(a.source_id); print("source ->", a.source_id)
    elif a.cmd == "listen": tv.listen(a.seconds)


if __name__ == "__main__":
    main()

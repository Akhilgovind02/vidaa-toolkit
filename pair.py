#!/usr/bin/env python3
"""
pair.py — one-time pairing with a VIDAA TV. Connects, triggers the on-screen PIN,
then you type the 4 digits; saves the returned token to tokens.json.

Config via environment (see config.example.env): VIDAA_TV_IP, VIDAA_CERT, VIDAA_KEY,
VIDAA_TV_MAC (optional), VIDAA_PROFILE (default modern).
"""
from __future__ import annotations
import json, ssl, threading, time
import paho.mqtt.client as mqtt
from vidaa import Tv, PORT

tv = Tv()
UI, PLAT, MOB = tv.ui, tv.platform, tv.mobile
state = {"connected": False, "pin_prompted": False, "token": None}


def on_connect(c, u, fl, reason, props=None):
    rc = getattr(reason, "value", reason)
    print(f"[connect] rc={rc}")
    if rc == 0:
        state["connected"] = True
        c.subscribe([
            (MOB + "ui_service/data/authentication", 0),
            (MOB + "ui_service/data/authenticationcode", 0),
            (MOB + "platform_service/data/tokenissuance", 0),
        ])


def on_message(c, u, m):
    p = m.payload.decode("utf-8", "replace")
    t = m.topic
    if t.endswith("ui_service/data/authentication"):
        state["pin_prompted"] = True
    elif t.endswith("ui_service/data/authenticationcode"):
        print("[pin result]", p)
    elif t.endswith("platform_service/data/tokenissuance"):
        try:
            d = json.loads(p)
            if "accesstoken" in d:
                state["token"] = d
        except Exception:
            pass


c = tv._client()
c.on_connect = on_connect
c.on_message = on_message
print(f"[*] client_id={tv.cid}")
print(f"[*] connecting {tv.ip}:{PORT} ...")
c.connect(tv.ip, PORT, 30)
c.loop_start()

for _ in range(50):
    if state["connected"]:
        break
    time.sleep(0.2)
if not state["connected"]:
    raise SystemExit("could not connect (rc!=0). Wrong/old client cert, or wrong profile. See PROTOCOL.md.")

time.sleep(0.5)
for i in range(3):
    print(f"[*] requesting PIN (attempt {i+1}) — look at the TV")
    c.publish(UI + "actions/vidaa_app_connect", '{"app_version":2,"connect_result":0,"device_type":"Mobile App"}')
    for _ in range(15):
        if state["pin_prompted"]:
            break
        time.sleep(0.2)
    if state["pin_prompted"]:
        break

pin = input("Enter the 4-digit PIN shown on the TV: ").strip()
c.publish(UI + "actions/authenticationcode", json.dumps({"authNum": int(pin)}))
time.sleep(1.0)
c.publish(PLAT + "data/gettoken", '{"refreshtoken": ""}')
c.publish(UI + "actions/authenticationcodeclose")

for _ in range(30):
    if state["token"]:
        break
    time.sleep(0.5)
c.loop_stop(); c.disconnect()

if state["token"]:
    with open("tokens.json", "w") as f:
        json.dump({**state["token"], "client_id": tv.cid}, f, indent=2)
    print("[*] paired — token saved to tokens.json")
else:
    print("[!] no token (wrong/expired PIN?). Re-run and try again.")

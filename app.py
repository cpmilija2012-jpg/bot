import asyncio
import aiohttp
import json
import re
import time
import struct
import hashlib
import logging
import os
import random as _rnd_cars
import requests as _req_cars
from copy import deepcopy
from html import escape
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
try:
    import brotli5
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False
import zlib
import base64
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, BotCommand,
)

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8927569360:AAFe6_WPmum6non8e-f9DQ7jE7rKGWq2H6E")
OWNER_ID  = 7549920418
RATE_LIMIT_ACTIONS = 10
RATE_LIMIT_SECONDS = 60
FK       = "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ"
LOAD_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetPlayerRecords3"
SAVE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SavePlayerRecordsPartially8"
RANK_URL = "https://us-central1-cp-multiplayer.cloudfunctions.net/SetUserRating4"
CAR_IDS = [59,133,132,13,53,99,100,102,37,21,48,77,74,2,23,51,163,186,158,55,
60,61,62,63,64,65,66,67,68,69,70,71,72,73,75,76,78,79,80,81,82,83,
84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,101,103,104,105,106,
107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,
124,125,126,127,128,129,130,131,134,135,136,137,138,139,140,141,142,
143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,159,160,
161,162,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,
179,180,181,182,183,184,185,187,188,189,190,191,192,193,194,195,196,
197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,
214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230]
MAX_MONEY = 50_000_000
MAX_COIN  = 500_000

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("CPM")

# ============================================================
# STORE
# ============================================================
STORE_PATH = Path("cpm_store.json")
DEFAULT_STORE = {
    "allowed_users": [],  "vip_users": [],  "admins": {},
    "pending": {},  "banned": [],  "expiry": {},
    "stats": {"total_logins": 0, "total_actions": 0, "total_unlocks": 0},
    "admin_log": [],  "users": {},  "daily_stats": {},
    "notes": {},  "warnings": {},
    "maintenance": False,  "broadcast_history": [],
    "bot_photo": "",
}

def load_store():
    try:
        if STORE_PATH.exists():
            with open(STORE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for k, v in DEFAULT_STORE.items():
                if k not in data:
                    data[k] = deepcopy(v)
            # Ensure types
            data["admins"]        = {str(k): v for k, v in data.get("admins", {}).items()}
            data["allowed_users"] = list({int(x) for x in data.get("allowed_users", [])})
            data["vip_users"]     = list({int(x) for x in data.get("vip_users", [])})
            data["banned"]        = list({int(x) for x in data.get("banned", [])})
            data["pending"]       = {str(k): v for k, v in data.get("pending", {}).items()}
            data["expiry"]        = {str(k): v for k, v in data.get("expiry", {}).items()}
            data["users"]         = {str(k): v for k, v in data.get("users", {}).items()}
            data["notes"]         = {str(k): v for k, v in data.get("notes", {}).items()}
            data["warnings"]      = {str(k): v for k, v in data.get("warnings", {}).items()}
            return data
    except Exception as e:
        log.error(f"Store load error: {e}")
    return deepcopy(DEFAULT_STORE)

def save_store(data):
    try:
        with open(STORE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
        return True
    except Exception as e:
        log.error(f"Store save error: {e}")
        return False

STORE = load_store()
ALLOWED_USERS = STORE.get("allowed_users", [])
BANNED        = STORE.get("banned", [])
VIP_USERS     = STORE.get("vip_users", [])
PENDING       = STORE.get("pending", {})
ADMINS        = STORE.get("admins", {})
ADMIN_LEVELS  = {"moderator": 1, "admin": 2, "superadmin": 3}

def is_allowed(uid):   return uid in ALLOWED_USERS
def is_banned(uid):    return uid in BANNED
def is_pending(uid):   return str(uid) in PENDING
def is_vip(uid):       return uid in VIP_USERS
def is_maintenance():  return STORE.get("maintenance", False)
def admin_level(uid):  return ADMIN_LEVELS.get(ADMINS.get(str(uid), ""), 0)
def admin_role(uid):   return ADMINS.get(str(uid), "")
def has_admin(uid, required="admin"):
    return admin_level(uid) >= ADMIN_LEVELS.get(required, 2)

def is_expired(uid):
    exp = STORE.get("expiry", {}).get(str(uid))
    if not exp: return False
    try:
        return datetime.fromisoformat(exp) < datetime.utcnow()
    except: return False

def check_rate_limit(uid):
    now = time.time()
    key = f"rl_{uid}"
    if key not in STORE:
        STORE[key] = []
    STORE[key] = [t for t in STORE[key] if now - t < RATE_LIMIT_SECONDS]
    if len(STORE[key]) >= RATE_LIMIT_ACTIONS:
        return False, RATE_LIMIT_SECONDS - int(now - STORE[key][0])
    STORE[key].append(now)
    return True, 0

def store_allow(uid, name="", save=True):
    if uid not in ALLOWED_USERS:
        ALLOWED_USERS.append(uid)
        STORE["allowed_users"] = ALLOWED_USERS
    if str(uid) in PENDING:
        del PENDING[str(uid)]
        STORE["pending"] = PENDING
    if uid in BANNED:
        BANNED.remove(uid)
        STORE["banned"] = BANNED
    STORE.setdefault("users", {})[str(uid)] = {"name": name, "added": datetime.utcnow().isoformat()}
    if save: save_store(STORE)

def store_ban(uid):
    if uid in ALLOWED_USERS: ALLOWED_USERS.remove(uid); STORE["allowed_users"] = ALLOWED_USERS
    if uid in VIP_USERS: VIP_USERS.remove(uid); STORE["vip_users"] = VIP_USERS
    if uid not in BANNED: BANNED.append(uid); STORE["banned"] = BANNED
    if str(uid) in PENDING: del PENDING[str(uid)]; STORE["pending"] = PENDING
    save_store(STORE)

def store_unban(uid):
    if uid in BANNED: BANNED.remove(uid); STORE["banned"] = BANNED; save_store(STORE)

def store_remove_user(uid):
    if uid in ALLOWED_USERS: ALLOWED_USERS.remove(uid); STORE["allowed_users"] = ALLOWED_USERS
    if uid in VIP_USERS: VIP_USERS.remove(uid); STORE["vip_users"] = VIP_USERS
    if str(uid) in PENDING: del PENDING[str(uid)]; STORE["pending"] = PENDING
    save_store(STORE)

def store_add_admin(uid, role="admin"):
    ADMINS[str(uid)] = role
    STORE["admins"] = ADMINS
    if uid not in ALLOWED_USERS: store_allow(uid, save=False)
    save_store(STORE)

def store_remove_admin(uid):
    if str(uid) in ADMINS: del ADMINS[str(uid)]; STORE["admins"] = ADMINS; save_store(STORE)

def store_add_pending(uid, name, username=""):
    PENDING[str(uid)] = {"name": name, "username": username, "time": datetime.utcnow().isoformat()}
    STORE["pending"] = PENDING
    save_store(STORE)

def store_add_vip(uid):
    if uid not in VIP_USERS: VIP_USERS.append(uid); STORE["vip_users"] = VIP_USERS; save_store(STORE)

def store_remove_vip(uid):
    if uid in VIP_USERS: VIP_USERS.remove(uid); STORE["vip_users"] = VIP_USERS; save_store(STORE)

def store_set_expiry(uid, days):
    exp = (datetime.utcnow() + timedelta(days=int(days))).isoformat()
    STORE.setdefault("expiry", {})[str(uid)] = exp
    save_store(STORE)

def store_remove_expiry(uid):
    if str(uid) in STORE.get("expiry", {}): del STORE["expiry"][str(uid)]; save_store(STORE)

def admin_log(actor_id, action, target=""):
    STORE.setdefault("admin_log", []).append({
        "time": datetime.utcnow().isoformat(),
        "actor": actor_id,
        "action": action,
        "target": target
    })
    save_store(STORE)

def update_daily_stats(key="actions"):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    STORE.setdefault("daily_stats", {}).setdefault(today, {}).setdefault(key, 0)
    STORE["daily_stats"][today][key] += 1
    save_store(STORE)

def add_broadcast_history(actor_id, btype, content, sent, failed):
    STORE.setdefault("broadcast_history", []).append({
        "time": datetime.utcnow().isoformat(),
        "actor": actor_id,
        "type": btype,
        "content": content,
        "sent": sent,
        "failed": failed
    })
    save_store(STORE)

# ============================================================
# CRYPTO / DECODE (From bot-2)
# ============================================================
def make_xor_key(uid):
    h = hashlib.md5(uid.encode()).digest()
    return bytes([h[i % 16] for i in range(256)])

def xor_bytes(data, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def decompress(data):
    try:
        return zlib.decompress(data, -zlib.MAX_WBITS)
    except:
        try:
            return zlib.decompress(data)
        except:
            if HAS_BROTLI:
                try: return brotli.decompress(data)
                except: pass
    return None

def compress(data):
    return zlib.compress(data)

def decrypt_aes(data, key):
    if not HAS_CRYPTO: return None
    try:
        iv = data[:16]
        ct = data[16:]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size)
    except: return None

def encrypt_aes(data, key):
    if not HAS_CRYPTO: return None
    try:
        iv = os.urandom(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return iv + cipher.encrypt(pad(data, AES.block_size))
    except: return None

def _md5(t): return hashlib.md5(t.encode()).digest()
def _sha1(t): return hashlib.sha1(t.encode()).digest()[:16]

def build_aes_keys(uid, password=None, email=None):
    target = uid if uid else email
    k1 = _md5(target)
    k2 = _sha1(target)
    k3 = _md5(k1.hex() + k2.hex())
    if password:
        k4 = _sha1(password)
        k5 = _md5(k4.hex() + k3.hex())
        return [k1, k2, k3, k4, k5]
    if email:
        k4 = _sha1(email)
        k5 = _md5(k4.hex() + k3.hex())
        return [k1, k2, k3, k4, k5]
    return [k1, k2, k3]

class Reader:
    def __init__(self, data):
        self.buf = data
        self.pos = 0
    def has_bytes(self, n): return self.pos + n <= len(self.buf)
    def read_byte(self):
        if not self.has_bytes(1): return 0
        v = self.buf[self.pos]; self.pos += 1; return v
    def read_int(self):
        if not self.has_bytes(4): return 0
        v = struct.unpack("<i", self.buf[self.pos:self.pos+4])[0]; self.pos += 4; return v
    def read_float(self):
        if not self.has_bytes(4): return 0.0
        v = struct.unpack("<f", self.buf[self.pos:self.pos+4])[0]; self.pos += 4; return v
    def read_string(self):
        if not self.has_bytes(4): return ""
        ln = struct.unpack("<i", self.buf[self.pos:self.pos+4])[0]; self.pos += 4
        if ln <= 0: return ""
        if not self.has_bytes(ln): return ""
        v = self.buf[self.pos:self.pos+ln].decode("utf-8", errors="replace"); self.pos += ln; return v
    def read_list(self, item_fn):
        if not self.has_bytes(4): return []
        ln = struct.unpack("<i", self.buf[self.pos:self.pos+4])[0]; self.pos += 4
        return [item_fn() for _ in range(ln)]
    def read_dict(self):
        d = {}
        if not self.has_bytes(4): return d
        ln = struct.unpack("<i", self.buf[self.pos:self.pos+4])[0]; self.pos += 4
        for _ in range(ln):
            k = self.read_string()
            v = self.read_string()
            d[k] = v
        return d
    def read_equipment(self):
        if not self.has_bytes(4): return []
        ln = struct.unpack("<i", self.buf[self.pos:self.pos+4])[0]; self.pos += 4
        out = []
        for _ in range(ln):
            if not self.has_bytes(1): break
            typ = self.read_byte()
            if typ == 0:
                out.append({"type": 0, "id": self.read_int(), "color": self.read_int()})
            elif typ == 1:
                out.append({"type": 1, "id": self.read_int()})
            elif typ == 2:
                out.append({"type": 2, "id": self.read_int(), "color": self.read_int(), "float": self.read_float()})
            else:
                out.append({"type": typ, "id": self.read_int()})
        return out

def parse_player(buf):
    r = Reader(buf)
    if r.read_byte() == 0: return None
    p = {}
    p["Name"] = r.read_string(); p["money"] = r.read_int()
    p["coin"] = r.read_int(); p["localID"] = r.read_string()
    p["boughtFsos"] = r.read_list(r.read_int)
    def read_friend():
        r.read_byte()
        return {"id": r.read_string(), "Name": r.read_string(), "accountID": r.read_string()}
    p["FriendsID"] = r.read_list(read_friend)
    p["LevelsDoneTime"] = r.read_list(r.read_float)
    p["floats"] = r.read_list(r.read_float)
    p["integers"] = r.read_list(r.read_int)
    p["fcar"] = r.read_list(r.read_int)
    p["favouriteWheels"] = r.read_list(r.read_int)
    p["favouriteVinyls"] = r.read_list(r.read_int)
    p["favouriteEmojis"] = r.read_list(r.read_int)
    p["personEquipmentsMale"] = r.read_equipment()
    p["personEquipmentsFemale"] = r.read_equipment()
    if r.read_byte() == 0:
        p["platesData"] = None
    else:
        def read_vinyl():
            r.read_byte()
            def rv(): return {"x": r.read_float(), "y": r.read_float(), "z": r.read_float()}
            return {"vectors": r.read_list(rv), "v": r.read_list(r.read_string),
                    "floats": r.read_list(r.read_float), "text": r.read_string()}
        def read_plate():
            r.read_byte()
            return {"plateId": r.read_int(), "frontCarId": r.read_int(),
                    "rearCarId": r.read_int(), "vinyls": r.read_list(read_vinyl)}
        p["platesData"] = {"allPlates": r.read_list(read_plate)}
    if r.read_byte() == 0:
        p["carIDnStatus"] = None
    else:
        p["carIDnStatus"] = {
            "carGeneratedIDs": r.read_list(r.read_string),
            "carStatus": r.read_list(r.read_int),
        }
    p["allData"] = r.read_string()
    p["flags"] = r.read_dict()
    p["animations"] = r.read_list(r.read_int)
    p["emojiPacks"] = r.read_list(r.read_int)
    p["wheels"] = r.read_list(r.read_int)
    p["boughtPoliceLights"] = r.read_list(r.read_int)
    p["boughtPoliceSirens"] = r.read_list(r.read_int)
    return p

def try_parse(buf):
    candidates = [buf]
    d1 = decompress(buf)
    if d1:
        candidates.append(d1)
    d2 = decompress(d1)
    if d2: candidates.append(d2)
    for c in candidates:
        if not c: continue
        if len(c) > 0 and c[0] in (1, 17, 23, 24):
            try:
                p = parse_player(c)
                if p and p.get("Name") is not None: return p
            except: pass
        try:
            clean = c[3:] if (len(c) >= 3 and c[0] == 0xef and c[1] == 0xbb and c[2] == 0xbf) else c
            if clean and clean[0] == 123: return json.loads(clean.decode("utf-8"))
        except: pass
    return None

def decrypt_player_record(base64_text, uid, password=None, email=None):
    try:
        base64_text = base64_text.strip().replace("-", "+").replace("_", "/")
        missing_padding = len(base64_text) % 4
        if missing_padding:
            base64_text += '=' * (4 - missing_padding)
        buf = base64.b64decode(base64_text)
    except Exception as e:
        return {"success": False, "message": f"Bad base64 ({str(e)})"}
    
    if len(buf) < 10:
        return {"success": False, "message": "Record data too small"}
    
    for key in build_aes_keys(uid, password, email):
        dec = decrypt_aes(buf, key)
        if dec:
            parsed = try_parse(dec)
            if parsed: return {"success": True, "record": parsed}
            
    xk = make_xor_key(str(uid or email or ""))
    xdec = xor_bytes(buf, xk)
    parsed = try_parse(xdec)
    if parsed: return {"success": True, "record": parsed}
    
    for d in [decompress(buf), decompress(xdec)]:
        if d:
            parsed = try_parse(d)
            if parsed: return {"success": True, "record": parsed}
            
    return {"success": False, "message": "Decryption failed (Wrong credentials/key)"}

class Writer:
    def __init__(self): self._p = []
    def write_byte(self, v): self._p.append(bytes([v & 0xFF]))
    def write_int(self, v):  self._p.append(struct.pack("<i", int(v or 0)))
    def write_float(self, v): self._p.append(struct.pack("<f", float(v or 0.0)))
    def write_string(self, s):
        t = s.encode("utf-8") if s else b""
        self.write_int(len(t))
        self._p.append(t)
    def write_list(self, lst, fn):
        self.write_int(len(lst))
        for item in lst: fn(item)
    def write_dict(self, d):
        self.write_int(len(d))
        for k, v in d.items():
            self.write_string(k)
            self.write_string(v)
    def write_equipment(self, data):
        self.write_int(len(data))
        for item in data:
            t = item.get("type", 0)
            self.write_byte(t)
            if t == 0:
                self.write_int(item.get("id", 0)); self.write_int(item.get("color", 0))
            elif t == 1:
                self.write_int(item.get("id", 0))
            elif t == 2:
                self.write_int(item.get("id", 0)); self.write_int(item.get("color", 0)); self.write_float(item.get("float", 0.0))
            else:
                self.write_int(item.get("id", 0))
    def write_plates(self, data):
        if data is None:
            self.write_byte(0); return
        self.write_byte(1)
        def wv(v):
            self.write_byte(1)
            self.write_list(v.get("vectors", []), lambda x: (self.write_float(x["x"]), self.write_float(x["y"]), self.write_float(x["z"])))
            self.write_list(v.get("v", []), self.write_string)
            self.write_list(v.get("floats", []), self.write_float)
            self.write_string(v.get("text", ""))
        def wp(p):
            self.write_byte(1)
            self.write_int(p.get("plateId", 0)); self.write_int(p.get("frontCarId", 0)); self.write_int(p.get("rearCarId", 0))
            self.write_list(p.get("vinyls", []), wv)
        self.write_list(data.get("allPlates", []), wp)
    def write_car_id_status(self, data):
        if data is None:
            self.write_byte(0); return
        self.write_byte(1)
        self.write_list(data.get("carGeneratedIDs", []), self.write_string)
        self.write_list(data.get("carStatus", []), self.write_int)
    def to_bytes(self): return b"".join(self._p)

def serialize_player(p):
    w = Writer()
    w.write_byte(1)
    w.write_string(p.get("Name", ""))
    w.write_int(p.get("money", 0))
    w.write_int(p.get("coin", 0))
    w.write_string(p.get("localID", ""))
    w.write_list(p.get("boughtFsos", []), w.write_int)
    def wf(f):
        w.write_byte(1)
        w.write_string(f.get("id", ""))
        w.write_string(f.get("Name", ""))
        w.write_string(f.get("accountID", ""))
    w.write_list(p.get("FriendsID", []), wf)
    w.write_list(p.get("LevelsDoneTime", []), w.write_float)
    w.write_list(p.get("floats", []), w.write_float)
    w.write_list(p.get("integers", []), w.write_int)
    w.write_list(p.get("fcar", []), w.write_int)
    w.write_list(p.get("favouriteWheels", []), w.write_int)
    w.write_list(p.get("favouriteVinyls", []), w.write_int)
    w.write_list(p.get("favouriteEmojis", []), w.write_int)
    w.write_equipment(p.get("personEquipmentsMale", []))
    w.write_equipment(p.get("personEquipmentsFemale", []))
    w.write_plates(p.get("platesData", None))
    w.write_car_id_status(p.get("carIDnStatus", None))
    w.write_string(p.get("allData", ""))
    w.write_dict(p.get("flags", {}))
    w.write_list(p.get("animations", []), w.write_int)
    w.write_list(p.get("emojiPacks", []), w.write_int)
    w.write_list(p.get("wheels", []), w.write_int)
    w.write_list(p.get("boughtPoliceLights", []), w.write_int)
    w.write_list(p.get("boughtPoliceSirens", []), w.write_int)
    return w.to_bytes()

# ============================================================
# API (Game Record Load/Save)
# ============================================================
FIREBASE_LOGIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/"
    f"accounts:signInWithPassword?key={FK}"
)

async def firebase_login(session, email, password):
    payload = {
        "email": email, 
        "password": password, 
        "returnSecureToken": True,
        "clientType": "CLIENT_TYPE_ANDROID"
    }
    try:
        async with session.post(
            FIREBASE_LOGIN_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 200 and "idToken" in data:
                return data["idToken"], data.get("localId", "")
            err = data.get("error", {}).get("message", "")
            if "EMAIL_NOT_FOUND" in err or "INVALID_EMAIL" in err:
                return None, "Email not found. Check your email."
            if "INVALID_PASSWORD" in err or "INVALID_LOGIN_CREDENTIALS" in err:
                return None, "Wrong password. Please try again."
            if "USER_DISABLED" in err:
                return None, "Account is disabled."
            if "TOO_MANY_ATTEMPTS_TRY_LATER" in err:
                return None, "Too many failed attempts. Try again later."
            return None, err or f"Firebase error (HTTP {resp.status})"
    except Exception as e:
        return None, f"Network error: {str(e)}"

async def api_load_record(session, email="", password=""):
    id_token, firebase_uid = await firebase_login(session, email, password)
    if not id_token:
        return {"success": False, "message": firebase_uid}
    
    payload = {
        "email": email,
        "password": password,
        "uid": firebase_uid,
        "fk": FK,
    }
    try:
        async with session.post(LOAD_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()
            if resp.status != 200:
                try:
                    err_data = json.loads(text)
                    err_msg = err_data.get("error") or err_data.get("message") or err_data.get("detail") or text[:300]
                except Exception:
                    err_msg = text[:300] if text else f"HTTP {resp.status}"
                return {"success": False, "message": err_msg}
            
            b64 = ""
            extracted_uid = ""
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    if "error" in data:
                        return {"success": False, "message": data["error"]}
                    b64 = data.get("base64") or data.get("record") or ""
                    extracted_uid = data.get("uid") or ""
            except json.JSONDecodeError:
                b64 = text
            
            b64 = b64.strip().replace("\r", "").replace("\n", "").replace(" ", "").replace("\t", "")
            if not b64:
                return {"success": False, "message": "Empty response from server"}
            
            uid_to_use = extracted_uid or firebase_uid
            res = decrypt_player_record(b64, uid_to_use, password, email)
            if res.get("success"):
                res["uid"] = uid_to_use
            return res
    except Exception as e:
        return {"success": False, "message": f"Network error: {str(e)}"}

async def api_save_record(session, uid, record, password="", email=""):
    raw = serialize_player(record)
    if not raw or len(raw) == 0:
        return {"success": False, "message": "Serialize failed"}
    comp = compress(raw)
    b64 = base64.b64encode(comp).decode()
    payload = {
        "uid": uid,
        "password": password,
        "email": email,
        "fk": FK,
        "base64": b64,
    }
    try:
        async with session.post(SAVE_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()
            return {"success": True, "response": text}
    except Exception as e:
        return {"success": False, "message": str(e)}

async def api_set_rank(session, uid, rank):
    payload = {"uid": uid, "rank": rank, "fk": FK}
    try:
        async with session.post(RANK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            return {"success": resp.status == 200, "response": await resp.text()}
    except Exception as e:
        return {"success": False, "message": str(e)}

# ============================================================
# CLONE & UNLOCK CARS FEATURES (From main-1)
# ============================================================
_CPM1_FB_KEY = "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"
SOURCE_ACCOUNT = ("primocloneacc1@gmail.com", "123456")

def verify_user(email, password):
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
        "clientType": "CLIENT_TYPE_ANDROID",
    }
    try:
        response = _req_cars.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
            json=payload,
            params={"key": _CPM1_FB_KEY},
            timeout=30,
        )
        if response.status_code == 200:
            d = response.json()
            return d.get("idToken"), d.get("localId")
        return None, None
    except Exception:
        return None, None

def cpm1_api(token, endpoint, data=None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        response = _req_cars.post(
            f"https://europe-west1-cp-multiplayer.cloudfunctions.net/{endpoint}",
            json={"data": data},
            headers=headers,
            timeout=60,
        )
        return response.status_code, response.text
    except Exception:
        return 500, json.dumps({"result": "error"})

def cpm1_get_cars(token):
    status, text = cpm1_api(token, "GetAllCars2", None)
    if status != 200:
        return None
    try:
        result = json.loads(json.loads(text)["result"])
        return result if isinstance(result, list) else None
    except Exception:
        return None

def cpm1_get_garage_slot(token):
    for attempt in range(5):
        try:
            status, text = cpm1_api(token, "WSGetCarListV3", 20)
            if status == 200:
                try:
                    data = json.loads(text)
                    result = json.loads(data["result"])
                    if result and isinstance(result, list) and len(result) > 0:
                        for slot in result:
                            if slot.get("carID", 0) == 0:
                                return slot
                        return result[0]
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.5)
    try:
        status, text = cpm1_api(token, "WSGetCarListV3", 20)
        if status == 200:
            try:
                data = json.loads(text)
                result = json.loads(data["result"])
                if result and isinstance(result, list) and len(result) > 0:
                    return result[0]
            except Exception:
                pass
    except Exception:
        pass
    return None

def cpm1_get_full_car(token, car_data):
    cid = car_data.get("CarID") or car_data.get("carID") or 0
    gen = car_data.get("carGeneratedID") or car_data.get("CarGeneratedID") or ""
    for endpoint, data in (
        ("WSGetFullCarV3", json.dumps({"CarID": cid, "carGeneratedID": gen})),
        ("WSGetFullCarV3", json.dumps(car_data)),
        ("WSGetFullCarV3", json.dumps({"CarID": cid})),
        ("TestGetAllCars", None),
    ):
        try:
            status, text = cpm1_api(token, endpoint, data)
            if status != 200:
                continue
            raw = json.loads(text)
            result = raw.get("result", raw)
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    pass
            if isinstance(result, dict) and (result.get("CarID") or result.get("carID")):
                return result
            if isinstance(result, list) and result:
                for item in result:
                    if not isinstance(item, dict):
                        continue
                    if item.get("CarID") == cid or item.get("carID") == cid:
                        return item
        except Exception:
            continue
    return None

def cpm1_fix_car_appearance(car):
    if not isinstance(car, dict):
        return car
    car = json.loads(json.dumps(car))
    vyn = car.get("Vynils")
    if not isinstance(vyn, dict):
        vyn = {}
    if "CarID" not in vyn and car.get("CarID") is not None:
        vyn["CarID"] = car.get("CarID")
    car["Vynils"] = vyn
    
    def ensure_color_list(key, length, default=1.0):
        val = car.get(key)
        if not isinstance(val, list) or len(val) == 0:
            car[key] = [float(default)] * length
        else:
            fixed = []
            for x in val:
                try:
                    fx = float(x)
                except Exception:
                    fx = default
                if fx == 0.0:
                    fx = 0.15
                fixed.append(fx)
            car[key] = fixed

    for key, ln in (("colors", 4), ("Colors", 4), ("bodyColor", 4), ("paint", 4)):
        if key in car or key in ("colors", "Colors"):
            ensure_color_list(key, ln, 0.85)
            
    if isinstance(car.get("color"), (int, float)) and float(car.get("color") or 0) == 0:
        car["color"] = 1
    car["police"] = True if car.get("police") is None else car.get("police")
    car["isLocked"] = False
    if car.get("engineID") in (None, 0):
        car["engineID"] = 5
    car["cdi"] = True
    car["torque"] = car.get("torque") or 3000.0
    car["brake"] = car.get("brake") or 3000.0
    car["mass"] = car.get("mass") or 1100.0
    return car

def cpm1_clone_car(token_target, car_data, target_uid, token_source=None):
    cid = car_data.get("CarID", 0) or car_data.get("carID", 0)
    full = None
    if token_source:
        try:
            full = cpm1_get_full_car(token_source, car_data)
        except Exception:
            full = None
    
    base = full if isinstance(full, dict) else car_data
    car = cpm1_fix_car_appearance(base)
    car["CarID"] = cid
    
    try:
        if "texts" in car and isinstance(car["texts"], list) and len(car["texts"]) > 2:
            car["texts"][2] = f"{str(target_uid)[:8].upper()}_{cid} HZ"
        elif "texts" in car and isinstance(car["texts"], str):
            car["texts"] = ["", "", f"{str(target_uid)[:8].upper()} {cid}_HZ"]
    except Exception:
        pass
        
    try:
        if isinstance(car.get("Vynils"), dict):
            car["Vynils"]["CarID"] = cid
    except Exception:
        pass

    slot = cpm1_get_garage_slot(token_target)
    if not slot:
        return False
        
    vynil = car.get("Vynils") if isinstance(car.get("Vynils"), dict) else {}
    if not vynil:
        vynil = {"CarID": cid}
        
    payload = {
        "ownerID": slot.get("ownerID", ""),
        "ownerName": slot.get("ownerName", ""),
        "description": slot.get("description", ""),
        "CarID": slot.get("carID", 0),
        "carGeneratedID": slot.get("carGeneratedID", ""),
        "ownerAccountID": slot.get("ownerAccountID", ""),
        "oneCar": car,
        "vynilOneCar": vynil,
        "loadedLocalCar": {"instanceID": _rnd_cars.randint(-999999, -100000)},
        "price": slot.get("price", 100),
        "SellingCar": {},
        "willReject": False,
        "dislike": 1,
        "like": 0,
        "liked": False,
        "disliked": False,
        "mode": 1,
    }
    status, text = cpm1_api(token_target, "WSPurchaseCarV3", json.dumps(payload))
    try:
        if status == 200 and str(json.loads(text).get("result")) in ("1", 1):
            return True
    except Exception:
        pass
    return False

def cpm1_inject_car(email, password, car_id):
    try:
        tok, uid = verify_user(email, password)
        if not tok:
            return False
        stok, _ = verify_user(*SOURCE_ACCOUNT)
        if not stok:
            return False 
            
        status, text = cpm1_api(stok, "GetAllCars2", None)
        if status != 200:
            return False
        try:
            cars = json.loads(json.loads(text)["result"])
        except Exception:
            return False
        if not cars:
            return False
            
        tpl = max(cars, key=lambda c: c.get("CarID", 0))
        car = json.loads(json.dumps(tpl))
        car["CarID"] = car_id
        car = cpm1_fix_car_appearance(car)
        car["CarID"] = car_id
        
        try:
            if "texts" in car and isinstance(car["texts"], list) and len(car["texts"]) > 2:
                car["texts"][2] = f"{uid[:8].upper()}_{car_id}_HZ"
        except Exception:
            pass
            
        try:
            if isinstance(car.get("Vynils"), dict):
                car["Vynils"]["CarID"] = car_id
        except Exception:
            pass
            
        slot = cpm1_get_garage_slot(tok)
        if not slot:
            return False
            
        payload = {
            "ownerID": slot.get("ownerID", ""),
            "ownerName": slot.get("ownerName", ""),
            "description": slot.get("description", ""),
            "CarID": slot.get("carID", 0),
            "carGeneratedID": slot.get("carGeneratedID", ""),
            "ownerAccountID": slot.get("ownerAccountID", ""),
            "oneCar": car,
            "vynilOneCar": car.get("Vynils", {}),
            "loadedLocalCar": {"instanceID": _rnd_cars.randint(-999999, -100000)},
            "price": slot.get("price", 100),
            "SellingCar": {},
            "willReject": False,
            "dislike": 1,
            "like": 0,
            "liked": False,
            "disliked": False,
            "mode": 1,
        }
        status, text = cpm1_api(tok, "WSPurchaseCarV3", json.dumps(payload))
        try:
            result = json.loads(text)
            return status == 200 and str(result.get("result")) in ("1", "true", "True")
        except Exception:
            return False
    except Exception:
        return False

def cpm1_unlock_cars_on_account(email, password, car_ids=None, progress_cb=None):
    token, uid = verify_user(email, password)
    if not token:
        return False, {"error": "Login failed", "success": 0, "fail": 0, "total": 0}
    
    if not car_ids:
        car_ids = list(range(1, 271))
        
    existing = cpm1_get_cars(token) or []
    template = existing[0] if existing else {"CarID": 1, "Vynils": {"CarID": 1}, "engineID": 5}
    
    ok = fail = 0
    total = len(car_ids)
    
    for i, cid in enumerate(car_ids, 1):
        car = json.loads(json.dumps(template))
        car["CarID"] = int(cid)
        if isinstance(car.get("Vynils"), dict):
            car["Vynils"]["CarID"] = int(cid)
        else:
            car["Vynils"] = {"CarID": int(cid)}
        car = cpm1_fix_car_appearance(car)
        
        if cpm1_clone_car(token, car, uid, token_source=token):
            ok += 1
        else:
            try:
                if cpm1_inject_car(email, password, int(cid)):
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
                
        if progress_cb:
            try:
                progress_cb(i, total, ok, fail)
            except Exception:
                pass
        time.sleep(0.55)
        
    return (ok > 0), {"success": ok, "fail": fail, "total": total}

# ============================================================
# BOT SETUP
# ============================================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ============================================================
# FSM STATES
# ============================================================
class MenuState(StatesGroup):
    main = State()
    account = State()
    stats = State()
    cars = State()
    unlocks = State()
    admin = State()

class InputState(StatesGroup):
    custom_money = State()
    custom_coins = State()
    set_name = State()
    set_id = State()
    change_email = State()
    change_password = State()
    clone_target = State()
    copy_plates_target = State()
    buy_car_id = State()
    police_car_id = State()
    vinyls_car_id = State()
    race_wins = State()
    race_loses = State()
    king_rank = State()
    broadcast = State()
    add_user = State()
    remove_user = State()
    ban_user = State()
    unban_user = State()
    add_admin = State()
    remove_admin = State()
    add_vip = State()
    remove_vip = State()
    set_expiry = State()
    login_email = State()
    login_pass = State()
    clone_source_email = State()
    clone_source_pass = State()
    clone_target_email = State()
    clone_target_pass = State()
    unlock_cars_email = State()
    unlock_cars_pass = State()

# ============================================================
# KEYBOARDS
# ============================================================
def kb_main(is_admin=False):
    buttons = [
        [InlineKeyboardButton(text="Login", callback_data="do_login")],
        [InlineKeyboardButton(text="Save Account", callback_data="do_save")],
        [InlineKeyboardButton(text="Account", callback_data="menu_account")],
        [InlineKeyboardButton(text="Stats & Money", callback_data="menu_stats")],
        [InlineKeyboardButton(text="Cars & Garage", callback_data="menu_cars")],
        [InlineKeyboardButton(text="Unlocks & Extras", callback_data="menu_unlocks")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="Admin Panel", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_account():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Info", callback_data="acc_info"),
         InlineKeyboardButton(text="Set Name", callback_data="acc_set_name")],
        [InlineKeyboardButton(text="Set ID", callback_data="acc_set_id"),
         InlineKeyboardButton(text="Change Email", callback_data="acc_change_email")],
        [InlineKeyboardButton(text="Change Password", callback_data="acc_change_password"),
         InlineKeyboardButton(text="Clone Account", callback_data="acc_clone")],
        [InlineKeyboardButton(text="Copy Plates", callback_data="acc_copy_plates")],
        [InlineKeyboardButton(text="Back", callback_data="menu_main")],
    ])

def kb_stats():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Money 50M", callback_data="stat_money_max"),
         InlineKeyboardButton(text="Coins 500K", callback_data="stat_coins_max")],
        [InlineKeyboardButton(text="Custom Money", callback_data="stat_money_custom"),
         InlineKeyboardButton(text="Custom Coins", callback_data="stat_coins_custom")],
        [InlineKeyboardButton(text="Race Wins", callback_data="stat_race_wins"),
         InlineKeyboardButton(text="Race Loses", callback_data="stat_race_loses")],
        [InlineKeyboardButton(text="King Rank", callback_data="stat_king_rank")],
        [InlineKeyboardButton(text="Back", callback_data="menu_main")],
    ])

def kb_cars():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Unlock All Cars", callback_data="car_unlock_all"),
         InlineKeyboardButton(text="Buy Car (ID)", callback_data="car_buy_id")],
        [InlineKeyboardButton(text="Bumpers All", callback_data="car_bumpers_all"),
         InlineKeyboardButton(text="Bumpers Single", callback_data="car_bumpers_single")],
        [InlineKeyboardButton(text="Chrome All", callback_data="car_chrome_all"),
         InlineKeyboardButton(text="Chrome Single", callback_data="car_chrome_single")],
        [InlineKeyboardButton(text="Preset All", callback_data="car_preset_all"),
         InlineKeyboardButton(text="Preset Single", callback_data="car_preset_single")],
        [InlineKeyboardButton(text="Police All", callback_data="car_police_all"),
         InlineKeyboardButton(text="Police Single", callback_data="car_police_single")],
        [InlineKeyboardButton(text="Clone All", callback_data="car_clone_all"),
         InlineKeyboardButton(text="Clone Single", callback_data="car_clone_single")],
        [InlineKeyboardButton(text="Vinyls All", callback_data="car_vinyls_all"),
         InlineKeyboardButton(text="Vinyls Single", callback_data="car_vinyls_single")],
        [InlineKeyboardButton(text="Back", callback_data="menu_main")],
    ])

def kb_unlocks():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="W16", callback_data="unl_w16"),
         InlineKeyboardButton(text="Smoke", callback_data="unl_smoke")],
        [InlineKeyboardButton(text="Fuel", callback_data="unl_fuel"),
         InlineKeyboardButton(text="No Damage", callback_data="unl_nodamage")],
        [InlineKeyboardButton(text="Horns", callback_data="unl_horns"),
         InlineKeyboardButton(text="Animations", callback_data="unl_animations")],
        [InlineKeyboardButton(text="Perks", callback_data="unl_perks"),
         InlineKeyboardButton(text="Headlights", callback_data="unl_headlights")],
        [InlineKeyboardButton(text="Paid House", callback_data="unl_paidhouse"),
         InlineKeyboardButton(text="All Houses", callback_data="unl_allhouses")],
        [InlineKeyboardButton(text="Sirens", callback_data="unl_sirens"),
         InlineKeyboardButton(text="All Levels", callback_data="unl_alllevels")],
        [InlineKeyboardButton(text="All Clothes", callback_data="unl_allclothes")],
        [InlineKeyboardButton(text="Back", callback_data="menu_main")],
    ])

def kb_admin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add User", callback_data="adm_add_user"),
         InlineKeyboardButton(text="Remove User", callback_data="adm_remove_user")],
        [InlineKeyboardButton(text="Ban", callback_data="adm_ban"),
         InlineKeyboardButton(text="Unban", callback_data="adm_unban")],
        [InlineKeyboardButton(text="Add VIP", callback_data="adm_add_vip"),
         InlineKeyboardButton(text="Remove VIP", callback_data="adm_remove_vip")],
        [InlineKeyboardButton(text="Add Admin", callback_data="adm_add_admin"),
         InlineKeyboardButton(text="Remove Admin", callback_data="adm_remove_admin")],
        [InlineKeyboardButton(text="Broadcast", callback_data="adm_broadcast"),
         InlineKeyboardButton(text="Stats", callback_data="adm_stats")],
        [InlineKeyboardButton(text="Maintenance", callback_data="adm_maintenance"),
         InlineKeyboardButton(text="Logs", callback_data="adm_logs")],
        [InlineKeyboardButton(text="Back", callback_data="menu_main")],
    ])

def kb_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Cancel", callback_data="cancel")]
    ])

# ============================================================
# CHECKS
# ============================================================
async def check_user(message):
    uid = message.from_user.id
    if is_banned(uid):
        await message.answer("You are banned from using this bot.")
        return False
    if is_maintenance() and uid != OWNER_ID and not has_admin(uid, "admin"):
        await message.answer("Bot is under maintenance. Please try again later.")
        return False
    if not is_allowed(uid) and uid != OWNER_ID:
        await message.answer("You are not authorized. Request access with /start")
        return False
    if is_expired(uid):
        await message.answer("Your access has expired. Contact admin.")
        return False
    ok, wait = check_rate_limit(uid)
    if not ok:
        await message.answer(f"Rate limit! Wait {wait}s.")
        return False
    return True

async def check_callback(call):
    uid = call.from_user.id
    if is_banned(uid):
        await call.answer("Banned", show_alert=True)
        return False
    if is_maintenance() and uid != OWNER_ID and not has_admin(uid, "admin"):
        await call.answer("Maintenance", show_alert=True)
        return False
    if not is_allowed(uid) and uid != OWNER_ID:
        await call.answer("Not authorized", show_alert=True)
        return False
    return True

# ============================================================
# HANDLERS
# ============================================================
@router.message(CommandStart())
async def cmd_start(message, state):
    uid = message.from_user.id
    name = message.from_user.full_name
    if is_banned(uid):
        await message.answer("You are banned.")
        return
    if uid == OWNER_ID:
        store_allow(uid, name)
        store_add_admin(uid, "superadmin")
    if uid == OWNER_ID or is_allowed(uid):
        await message.answer(f"Welcome <b>{escape(name)}</b>! Choose a menu: ", reply_markup=kb_main(is_admin=has_admin(uid)))
        return
    if is_pending(uid):
        await message.answer("Your request is pending approval.")
        return
    store_add_pending(uid, name, message.from_user.username or "")
    await message.answer("Access request sent to admins. Please wait.")
    for aid in ADMINS:
        try:
            await bot.send_message(int(aid), f"New request from {escape(name)} (<code>{uid}</code>)")
        except: pass

@router.message(Command("help"))
async def cmd_help(message):
    if not await check_user(message): return
    text = """<b>Help</b>
/start - Main menu
/help - This message
Login first, then use menus to modify your account."""
    await message.answer(text)

@router.callback_query(F.data == "menu_main")
async def cb_main(call, state):
    if not await check_callback(call): return
    await state.set_state(MenuState.main)
    uid = call.from_user.id
    await call.message.edit_text("<b>Main Menu</b>\nLogin to load your account first.", reply_markup=kb_main(is_admin=has_admin(uid)))

@router.callback_query(F.data == "menu_account")
async def cb_menu_account(call, state):
    if not await check_callback(call): return
    await state.set_state(MenuState.account)
    await call.message.edit_text("<b>Account Menu</b>\nLogin first to use features.", reply_markup=kb_account())

@router.callback_query(F.data == "menu_stats")
async def cb_menu_stats(call, state):
    if not await check_callback(call): return
    await state.set_state(MenuState.stats)
    await call.message.edit_text("<b>Stats & Money</b>", reply_markup=kb_stats())

@router.callback_query(F.data == "menu_cars")
async def cb_menu_cars(call, state):
    if not await check_callback(call): return
    await state.set_state(MenuState.cars)
    await call.message.edit_text("<b>Cars & Garage</b>", reply_markup=kb_cars())

@router.callback_query(F.data == "menu_unlocks")
async def cb_menu_unlocks(call, state):
    if not await check_callback(call): return
    await state.set_state(MenuState.unlocks)
    await call.message.edit_text("<b>Unlocks & Extras</b>", reply_markup=kb_unlocks())

@router.callback_query(F.data == "menu_admin")
async def cb_menu_admin(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id):
        await call.answer("No access", show_alert=True)
        return
    await state.set_state(MenuState.admin)
    await call.message.edit_text("<b>Admin Panel</b>", reply_markup=kb_admin())

@router.callback_query(F.data == "do_login")
async def cb_do_login(call: CallbackQuery, state: FSMContext):
    if not await check_callback(call): return
    await state.set_state(InputState.login_email)
    await call.message.edit_text("Send your Game Email:", reply_markup=kb_cancel())

@router.message(InputState.login_email)
async def inp_login_email(message, state):
    if not await check_user(message): return
    em = message.text.strip()
    if not em or "@" not in em:
        await message.answer("⚠️ That doesn't look like a valid email. Please send your Game Email:", reply_markup=kb_cancel())
        return
    await state.update_data(login_email=em)
    await state.set_state(InputState.login_pass)
    await message.answer("Send your Password:", reply_markup=kb_cancel())

@router.message(InputState.login_pass)
async def inp_login_pass(message, state):
    if not await check_user(message): return
    pw = message.text.strip()
    data = await state.get_data()
    em = data.get("login_email", "")
    if not em:
        await message.answer("Session expired. Please press Login again.", reply_markup=kb_main(is_admin=has_admin(message.from_user.id)))
        await state.set_state(MenuState.main)
        return
    loading_msg = await message.answer("⏳ Loading account, please wait...")
    try:
        async with aiohttp.ClientSession() as session:
            res = await api_load_record(session, email=em, password=pw)
    except asyncio.TimeoutError:
        await loading_msg.edit_text("❌ Request timed out. Please try again.")
        await state.set_state(MenuState.main)
        return
    except Exception as e:
        await loading_msg.edit_text(f"❌ Connection error: {escape(str(e))}")
        await state.set_state(MenuState.main)
        return
    if not res.get("success"):
        err = escape(res.get("message", "Unknown error"))
        await loading_msg.edit_text(
            f"❌ Login failed: {err}\n\nPress Login to try again.",
            reply_markup=kb_main(is_admin=has_admin(message.from_user.id))
        )
        await state.set_state(MenuState.main)
        return
    rec = res.get("record")
    if not rec:
        await loading_msg.edit_text(
            "❌ Failed to parse account data. Check your credentials.",
            reply_markup=kb_main(is_admin=has_admin(message.from_user.id))
        )
        await state.set_state(MenuState.main)
        return
    uid = res.get("uid", "")
    await state.update_data(record=rec, uid=uid, password=pw, email=em)
    await loading_msg.edit_text(
        f"✅ Logged in as <b>{escape(rec.get('Name',''))}</b>\n"
        f"Money: {rec.get('money',0):,}\nCoins: {rec.get('coin',0):,}",
        reply_markup=kb_main(is_admin=has_admin(message.from_user.id))
    )
    await state.set_state(MenuState.main)
    STORE.setdefault("stats", {})["total_logins"] = STORE["stats"].get("total_logins", 0) + 1
    save_store(STORE)
    update_daily_stats("actions")

@router.callback_query(F.data == "do_save")
async def cb_do_save(call, state):
    if not await check_callback(call): return
    data = await state.get_data()
    rec = data.get("record")
    uid = data.get("uid", "")
    pw = data.get("password", "")
    em = data.get("email", "")
    if not rec:
        await call.answer("Login first!", show_alert=True)
        return
    await call.message.edit_text("Saving account...")
    async with aiohttp.ClientSession() as session:
        res = await api_save_record(session, uid, rec, pw, em)
    uid = call.from_user.id
    if res.get("success"):
        await call.message.edit_text("Account saved successfully!", reply_markup=kb_main(is_admin=has_admin(uid)))
    else:
        await call.message.edit_text(f"Save failed: {escape(res.get('message',''))}", reply_markup=kb_main(is_admin=has_admin(uid)))

@router.callback_query(F.data == "acc_info")
async def cb_acc_info(call, state):
    if not await check_callback(call): return
    data = await state.get_data()
    rec = data.get("record")
    if not rec:
        await call.answer("Login first!", show_alert=True)
        return
    text = f"""<b>Account Info</b>
Name: <code>{escape(rec.get('Name',''))}</code>
Money: <code>{rec.get('money',0):,}</code>
Coins: <code>{rec.get('coin',0):,}</code>
ID: <code>{escape(rec.get('localID',''))}</code>
Cars: <code>{len(rec.get('boughtFsos',[]))}</code>
Friends: <code>{len(rec.get('FriendsID',[]))}</code>
Animations: <code>{len(rec.get('animations',[]))}</code>
Wheels: <code>{len(rec.get('wheels',[]))}</code>"""
    await call.message.edit_text(text, reply_markup=kb_account())

@router.callback_query(F.data == "acc_set_name")
async def cb_acc_set_name(call, state):
    if not await check_callback(call): return
    await state.set_state(InputState.set_name)
    await call.message.edit_text("Send new name:", reply_markup=kb_cancel())

@router.message(InputState.set_name)
async def inp_set_name(message, state):
    if not await check_user(message): return
    data = await state.get_data()
    rec = data.get("record")
    if not rec:
        await message.answer("Login first!")
        await state.clear(); return
    rec["Name"] = message.text[:32]
    await state.update_data(record=rec)
    await message.answer(f"Name set to: <b>{escape(rec['Name'])}</b>", reply_markup=kb_account())
    await state.set_state(MenuState.account)

@router.callback_query(F.data == "acc_set_id")
async def cb_acc_set_id(call, state):
    if not await check_callback(call): return
    await state.set_state(InputState.set_id)
    await call.message.edit_text("Send new Local ID:", reply_markup=kb_cancel())

@router.message(InputState.set_id)
async def inp_set_id(message, state):
    if not await check_user(message): return
    data = await state.get_data()
    rec = data.get("record")
    if not rec:
        await message.answer("Login first!")
        await state.clear(); return
    rec["localID"] = message.text[:64]
    await state.update_data(record=rec)
    await message.answer(f"ID set to: <code>{escape(rec['localID'])}</code>", reply_markup=kb_account())
    await state.set_state(MenuState.account)

@router.callback_query(F.data == "acc_change_email")
async def cb_acc_change_email(call, state):
    if not await check_callback(call): return
    await state.set_state(InputState.change_email)
    await call.message.edit_text("Send new email:", reply_markup=kb_cancel())

@router.message(InputState.change_email)
async def inp_change_email(message, state):
    if not await check_user(message): return
    await state.update_data(email=message.text[:128])
    await message.answer("Email updated for next save.", reply_markup=kb_account())
    await state.set_state(MenuState.account)

@router.callback_query(F.data == "acc_change_password")
async def cb_acc_change_password(call, state):
    if not await check_callback(call): return
    await state.set_state(InputState.change_password)
    await call.message.edit_text("Send new password:", reply_markup=kb_cancel())

@router.message(InputState.change_password)
async def inp_change_password(message, state):
    if not await check_user(message): return
    await state.update_data(password=message.text[:64])
    await message.answer("Password updated for next save.", reply_markup=kb_account())
    await state.set_state(MenuState.account)

@router.callback_query(F.data == "acc_clone")
async def cb_acc_clone(call, state):
    if not await check_callback(call): return
    await state.set_state(InputState.clone_source_email)
    await call.message.edit_text(
        "<b>Clone Account</b>\n\nSend SOURCE account email:",
        reply_markup=kb_cancel()
    )

@router.message(InputState.clone_source_email)
async def inp_clone_source_email(message, state):
    if not await check_user(message): return
    await state.update_data(clone_source_email=message.text.strip())
    await state.set_state(InputState.clone_source_pass)
    await message.answer("Send SOURCE password:", reply_markup=kb_cancel())

@router.message(InputState.clone_source_pass)
async def inp_clone_source_pass(message, state):
    if not await check_user(message): return
    await state.update_data(clone_source_pass=message.text.strip())
    await state.set_state(InputState.clone_target_email)
    await message.answer("Send TARGET account email:", reply_markup=kb_cancel())

@router.message(InputState.clone_target_email)
async def inp_clone_target_email(message, state):
    if not await check_user(message): return
    await state.update_data(clone_target_email=message.text.strip())
    await state.set_state(InputState.clone_target_pass)
    await message.answer("Send TARGET password:", reply_markup=kb_cancel())

@router.message(InputState.clone_target_pass)
async def inp_clone_target_pass(message, state):
    if not await check_user(message): return
    d = await state.get_data()
    await state.clear()
    
    se = d.get("clone_source_email")
    sp = d.get("clone_source_pass")
    te = d.get("clone_target_email")
    tp = message.text.strip()
    
    m = await message.answer("<b>Cloning...</b>\nLogging into source...")
    
    source_token, source_uid = await asyncio.to_thread(verify_user, se, sp)
    if not source_token:
        await m.edit_text("❌ Source login failed.", reply_markup=kb_main(is_admin=has_admin(message.from_user.id)))
        return
        
    await m.edit_text("<b>Cloning...</b>\nFetching source cars...")
    cars = await asyncio.to_thread(cpm1_get_cars, source_token)
    if not cars:
        await m.edit_text("❌ Source has no cars.", reply_markup=kb_main(is_admin=has_admin(message.from_user.id)))
        return
        
    total = len(cars)
    await m.edit_text("<b>Cloning...</b>\nLogging into target...")
    target_token, target_uid = await asyncio.to_thread(verify_user, te, tp)
    if not target_token:
        await m.edit_text("❌ Target login failed.", reply_markup=kb_main(is_admin=has_admin(message.from_user.id)))
        return
        
    done = ok = fail = 0
    for idx, car in enumerate(cars):
        if not isinstance(car, dict):
            continue
        res = await asyncio.to_thread(cpm1_clone_car, target_token, car, target_uid, token_source=source_token)
        if res:
            ok += 1
        else:
            fail += 1
        done += 1
        pct = int((done / total) * 100)
        bar = "▰" * int(pct / 7) + "▱" * (15 - int(pct / 7))
        if idx % 2 == 0 or done == total:
            try:
                await m.edit_text(
                    f"<b>Cloning...</b>\n\n"
                    f"[{bar}] {pct}%\n"
                    f"✔ {ok} ✗ {fail} ▸ {done}/{total}\n\n"
                    f"⏳ Car {car.get('CarID', car.get('carID', '?'))}"
                )
            except Exception:
                pass
        await asyncio.sleep(0.6)
        
    if ok == total:
        txt = f"✅ Cloned {ok}/{total} cars"
    elif ok > 0:
        txt = f"⚠️ Partial {ok}/{total} (fail {fail})"
    else:
        txt = f"❌ All {total} cars failed"
        
    try:
        await m.edit_text(f"<b>Clone Complete</b>\n\n{txt}", reply_markup=kb_main(is_admin=has_admin(message.from_user.id)))
    except Exception:
        pass

@router.callback_query(F.data == "car_unlock_all")
async def cb_car_unlock_all(call, state):
    if not await check_callback(call): return
    await state.set_state(InputState.unlock_cars_email)
    await call.message.edit_text(
        "<b>Unlock All Cars</b>\n\nSend account email:",
        reply_markup=kb_cancel()
    )

@router.message(InputState.unlock_cars_email)
async def inp_unlock_cars_email(message, state):
    if not await check_user(message): return
    await state.update_data(unlock_cars_email=message.text.strip())
    await state.set_state(InputState.unlock_cars_pass)
    await message.answer("Send password:", reply_markup=kb_cancel())

@router.message(InputState.unlock_cars_pass)
async def inp_unlock_cars_pass(message, state):
    if not await check_user(message): return
    d = await state.get_data()
    await state.clear()
    
    email = d.get("unlock_cars_email")
    password = message.text.strip()
    
    m = await message.answer("<b>Unlocking Cars...</b>\nLogging in...")
    
    token, uid = await asyncio.to_thread(verify_user, email, password)
    if not token:
        await m.edit_text("❌ Login failed.", reply_markup=kb_main(is_admin=has_admin(message.from_user.id)))
        return
        
    car_ids = list(range(1, 51))
    total = len(car_ids)
    ok = fail = 0
    
    for i, cid in enumerate(car_ids):
        res = await asyncio.to_thread(cpm1_inject_car, email, password, cid)
        if res:
            ok += 1
        else:
            fail += 1
            
        pct = int(((i + 1) / total) * 100)
        bar = "▰" * int(pct / 7) + "▱" * (15 - int(pct / 7))
        if i % 3 == 0 or i == total - 1:
            try:
                await m.edit_text(
                    f"<b>Unlocking Cars...</b>\n\n"
                    f"[{bar}] {pct}%\n"
                    f"✔ {ok} ✗ {fail} ▸ {i+1}/{total}\n\n"
                    f"⏳ Car ID: {cid}"
                )
            except Exception:
                pass
        await asyncio.sleep(0.55)
        
    txt = f"{'✅' if ok > 0 else '❌'} {ok}/{total} unlocked (fail {fail})"
    try:
        await m.edit_text(f"<b>Unlock Complete</b>\n\n{txt}", reply_markup=kb_main(is_admin=has_admin(message.from_user.id)))
    except Exception:
        pass

@router.callback_query(F.data == "unl_allhouses")
async def cb_unl_allhouses(call, state):
    if not await check_callback(call): return
    data = await state.get_data()
    rec = data.get("record")
    if not rec:
        await call.answer("Login first!", show_alert=True); return
    flags = rec.get("flags", {}); flags["allhouses"] = "1"; rec["flags"] = flags
    await state.update_data(record=rec)
    await call.answer("All Houses unlocked", show_alert=True)

@router.callback_query(F.data == "unl_sirens")
async def cb_unl_sirens(call, state):
    if not await check_callback(call): return
    data = await state.get_data()
    rec = data.get("record")
    if not rec:
        await call.answer("Login first!", show_alert=True); return
    rec["boughtPoliceLights"] = list(range(1,50))
    rec["boughtPoliceSirens"] = list(range(1,50))
    await state.update_data(record=rec)
    await call.answer("Sirens unlocked", show_alert=True)

@router.callback_query(F.data == "unl_alllevels")
async def cb_unl_alllevels(call, state):
    if not await check_callback(call): return
    data = await state.get_data()
    rec = data.get("record")
    if not rec:
        await call.answer("Login first!", show_alert=True); return
    rec["LevelsDoneTime"] = [1.0]*50
    await state.update_data(record=rec)
    await call.answer("All Levels unlocked", show_alert=True)

@router.callback_query(F.data == "unl_allclothes")
async def cb_unl_allclothes(call, state):
    if not await check_callback(call): return
    data = await state.get_data()
    rec = data.get("record")
    if not rec:
        await call.answer("Login first!", show_alert=True); return
    male = []
    female = []
    for i in range(1,200):
        male.append({"type": 0, "id": i, "color": 0})
        female.append({"type": 0, "id": i, "color": 0})
    rec["personEquipmentsMale"] = male
    rec["personEquipmentsFemale"] = female
    await state.update_data(record=rec)
    await call.answer("All Clothes unlocked", show_alert=True)

@router.callback_query(F.data == "adm_add_user")
async def cb_adm_add_user(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    await state.set_state(InputState.add_user)
    await call.message.edit_text("Send User ID to add:", reply_markup=kb_cancel())

@router.message(InputState.add_user)
async def inp_add_user(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_allow(uid)
    admin_log(message.from_user.id, "add_user", str(uid))
    await message.answer(f"User {uid} added.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_remove_user")
async def cb_adm_remove_user(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    await state.set_state(InputState.remove_user)
    await call.message.edit_text("Send User ID to remove:", reply_markup=kb_cancel())

@router.message(InputState.remove_user)
async def inp_remove_user(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_remove_user(uid)
    admin_log(message.from_user.id, "remove_user", str(uid))
    await message.answer(f"User {uid} removed.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_ban")
async def cb_adm_ban(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    await state.set_state(InputState.ban_user)
    await call.message.edit_text("Send User ID to ban:", reply_markup=kb_cancel())

@router.message(InputState.ban_user)
async def inp_ban_user(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_ban(uid)
    admin_log(message.from_user.id, "ban", str(uid))
    await message.answer(f"User {uid} banned.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_unban")
async def cb_adm_unban(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    await state.set_state(InputState.unban_user)
    await call.message.edit_text("Send User ID to unban:", reply_markup=kb_cancel())

@router.message(InputState.unban_user)
async def inp_unban_user(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_unban(uid)
    admin_log(message.from_user.id, "unban", str(uid))
    await message.answer(f"User {uid} unbanned.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_add_vip")
async def cb_adm_add_vip(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    await state.set_state(InputState.add_vip)
    await call.message.edit_text("Send User ID to add VIP:", reply_markup=kb_cancel())

@router.message(InputState.add_vip)
async def inp_add_vip(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_add_vip(uid)
    admin_log(message.from_user.id, "add_vip", str(uid))
    await message.answer(f"User {uid} is now VIP.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_remove_vip")
async def cb_adm_remove_vip(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    await state.set_state(InputState.remove_vip)
    await call.message.edit_text("Send User ID to remove VIP:", reply_markup=kb_cancel())

@router.message(InputState.remove_vip)
async def inp_remove_vip(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_remove_vip(uid)
    admin_log(message.from_user.id, "remove_vip", str(uid))
    await message.answer(f"User {uid} VIP removed.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_add_admin")
async def cb_adm_add_admin(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "superadmin"):
        await call.answer("Superadmin only", show_alert=True); return
    await state.set_state(InputState.add_admin)
    await call.message.edit_text("Send User ID to add as admin:", reply_markup=kb_cancel())

@router.message(InputState.add_admin)
async def inp_add_admin(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_add_admin(uid, "admin")
    admin_log(message.from_user.id, "add_admin", str(uid))
    await message.answer(f"User {uid} is now admin.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_remove_admin")
async def cb_adm_remove_admin(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "superadmin"):
        await call.answer("Superadmin only", show_alert=True); return
    await state.set_state(InputState.remove_admin)
    await call.message.edit_text("Send User ID to remove admin:", reply_markup=kb_cancel())

@router.message(InputState.remove_admin)
async def inp_remove_admin(message, state):
    if not await check_user(message): return
    try: uid = int(message.text.strip())
    except: await message.answer("Invalid ID!"); return
    store_remove_admin(uid)
    admin_log(message.from_user.id, "remove_admin", str(uid))
    await message.answer(f"User {uid} admin removed.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_broadcast")
async def cb_adm_broadcast(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    await state.set_state(InputState.broadcast)
    await call.message.edit_text("Send broadcast message:", reply_markup=kb_cancel())

@router.message(InputState.broadcast)
async def inp_broadcast(message, state):
    if not await check_user(message): return
    text = message.text
    sent = 0
    failed = 0
    for uid in ALLOWED_USERS:
        try:
            await bot.send_message(uid, f"<b>Broadcast</b>\n{text}")
            sent += 1
        except: failed += 1
    add_broadcast_history(message.from_user.id, "text", text, sent, failed)
    await message.answer(f"Broadcast sent: {sent} ok, {failed} failed.", reply_markup=kb_admin())
    await state.set_state(MenuState.admin)

@router.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    stats = STORE.get("stats", {})
    today = datetime.utcnow().strftime("%Y-%m-%d")
    daily = STORE.get("daily_stats", {}).get(today, {})
    text = f"""<b>Bot Stats</b>
Total Logins: {stats.get('total_logins',0)}
Total Actions: {stats.get('total_actions',0)}
Total Unlocks: {stats.get('total_unlocks',0)}
Allowed Users: {len(ALLOWED_USERS)}
VIP Users: {len(VIP_USERS)}
Banned: {len(BANNED)}
Pending: {len(PENDING)}
Admins: {len(ADMINS)}
Today Actions: {daily.get('actions',0)}
Today Unlocks: {daily.get('unlocks',0)}"""
    await call.message.edit_text(text, reply_markup=kb_admin())

@router.callback_query(F.data == "adm_maintenance")
async def cb_adm_maintenance(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "superadmin"):
        await call.answer("Superadmin only", show_alert=True); return
    STORE["maintenance"] = not STORE.get("maintenance", False)
    save_store(STORE)
    status = "ON" if STORE["maintenance"] else "OFF"
    await call.answer(f"Maintenance {status}", show_alert=True)
    await call.message.edit_text(f"<b>Admin Panel</b>\nMaintenance: {status}", reply_markup=kb_admin())

@router.callback_query(F.data == "adm_logs")
async def cb_adm_logs(call, state):
    if not await check_callback(call): return
    if not has_admin(call.from_user.id, "admin"):
        await call.answer("No access", show_alert=True); return
    logs = STORE.get("admin_log", [])[-20:]
    text = "<b>Recent Admin Logs</b>\n"
    for log_entry in logs:
        text += f"\n{escape(log_entry.get('action',''))} by {log_entry.get('actor','')} -> {escape(log_entry.get('target',''))}"
    if len(text) > 4000: text = text[:4000]
    await call.message.edit_text(text, reply_markup=kb_admin())

@router.callback_query(F.data == "cancel")
async def cb_cancel(call, state):
    if not await check_callback(call): return
    await state.clear()
    await state.set_state(MenuState.main)
    uid = call.from_user.id
    await call.message.edit_text("<b>Main Menu</b>", reply_markup=kb_main(is_admin=has_admin(uid)))

# ============================================================
# RENDER HEALTH CHECK SERVER (keeps service alive)
# ============================================================
async def health_check_server():
    from aiohttp import web
    app = web.Application()
    async def health(request):
        return web.Response(text="OK", status=200)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Health check server running on port {port}")

# ============================================================
# MAIN
# ============================================================
async def main():
    await health_check_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

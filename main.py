import os
import sys
import platform
import subprocess
import importlib
import importlib.util
import hashlib as _hl
import shutil

# =========================================================
# 0. PORTABLE AUTO-BOOTSTRAP
#    Creates a private virtual environment NEXT TO THIS FILE
#    (.venv_win / .venv_mac / .venv_linux), installs every
#    package there, then relaunches itself inside it.
#    Nothing is ever installed into the global Python.
# =========================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
FLET_VERSION = "0.28.3"   # change here if you want a different Flet version

# (import name, [pip specs tried in order], required?)
REQUIREMENTS = [
    ("requests",       ["requests"],                                            True),
    ("flet",           [f"flet[all]=={FLET_VERSION}", f"flet=={FLET_VERSION}"], True),
    ("pygame",         ["pygame", "pygame-ce"],                                 False),
    ("numpy",          ["numpy"],                                               False),
    ("cv2",            ["opencv-python"],                                       False),
    ("mss",            ["mss"],                                                 False),
    ("imageio_ffmpeg", ["imageio-ffmpeg"],                                      False),
    ("faster_whisper", ["faster-whisper"],                                      False),
    ("edge_tts",       ["edge-tts"],                                            False),
    ("pyperclip",      ["pyperclip"],                                           False),
]

_OSTAG = {"Windows": "win", "Darwin": "mac"}.get(platform.system(), "linux")
VENV_DIR = os.path.join(APP_DIR, ".venv_" + _OSTAG)
_STAMP = os.path.join(VENV_DIR, ".deps_ok")


def _is_android_early():
    return (os.environ.get("FLET_PLATFORM", "").lower() == "android"
            or "ANDROID_ROOT" in os.environ or "ANDROID_DATA" in os.environ
            or "android" in platform.platform().lower() or hasattr(sys, "getandroidapilevel"))


def _is_packaged():
    """True inside an APK / `flet build` app (no venv bootstrap there)."""
    return bool(os.environ.get("FLET_APP_STORAGE_DATA")) or getattr(sys, "frozen", False)


def _say(*args):
    try:
        print(*args, flush=True)
    except Exception:
        pass


def _wait_for_enter(msg="\nPress Enter to close this window..."):
    try:
        input(msg)
    except Exception:
        pass


def _venv_python():
    if os.name == "nt":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def _in_our_venv():
    try:
        return os.path.normcase(os.path.realpath(sys.prefix)) == os.path.normcase(os.path.realpath(VENV_DIR))
    except Exception:
        return False


def _quiet_kw():
    kw = {}
    if sys.stdout is None:  # pythonw.exe (no console)
        kw["stdout"] = subprocess.DEVNULL
        kw["stderr"] = subprocess.DEVNULL
        if os.name == "nt":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kw


def _venv_healthy():
    py = _venv_python()
    if not os.path.exists(py):
        return False
    try:
        return subprocess.call([py, "-c", "import sys, pip"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def _ensure_venv():
    if _venv_healthy():
        return True
    if os.path.isdir(VENV_DIR):  # moved to another PC / other Python -> rebuild
        _say(" Existing environment is not valid here, rebuilding...")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
    _say(" Creating private environment next to the app (portable)...")
    try:
        subprocess.call([sys.executable, "-m", "venv", VENV_DIR], **_quiet_kw())
    except Exception as e:
        _say(f" venv creation error: {e}")
    return _venv_healthy()


def _pip_install(py, spec):
    cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", spec]
    try:
        return subprocess.call(cmd, **_quiet_kw()) == 0
    except Exception as e:
        _say(f"      pip error: {e}")
        return False


def _missing_in(py):
    mods = [r[0] for r in REQUIREMENTS] + ["flet_desktop"]
    code = "import importlib.util as u,sys\nprint(','.join(m for m in sys.argv[1:] if u.find_spec(m) is None))"
    try:
        out = subprocess.check_output([py, "-c", code] + mods, text=True, stderr=subprocess.DEVNULL).strip()
        return [m for m in out.split(",") if m]
    except Exception:
        return [r[0] for r in REQUIREMENTS]


def _stamp_value():
    return _hl.md5((str(REQUIREMENTS) + sys.version.split()[0]).encode()).hexdigest()


def _install_requirements(py):
    try:
        with open(_STAMP) as f:
            if f.read().strip() == _stamp_value() and not _missing_in(py):
                return
    except Exception:
        pass

    missing = _missing_in(py)
    if not missing:
        try:
            with open(_STAMP, "w") as f:
                f.write(_stamp_value())
        except Exception:
            pass
        return

    _say("=" * 60)
    _say(" Daily Devotional - first-time setup (installing into local .venv)")
    _say(" This only happens once. Please keep this window open...")
    _say("=" * 60)

    failed_req, failed_opt = [], []
    for mod, specs, required in REQUIREMENTS:
        if mod not in missing:
            continue
        ok = False
        for spec in specs:
            _say(f"\n >> Installing {spec} ...")
            if _pip_install(py, spec) and mod not in _missing_in(py):
                ok = True
                break
        if not ok:
            (failed_req if required else failed_opt).append(mod)

    if "flet_desktop" in _missing_in(py) and "flet" not in failed_req:
        _say(f"\n >> Installing flet-desktop=={FLET_VERSION} ...")
        _pip_install(py, f"flet-desktop=={FLET_VERSION}")

    if failed_req:
        _say("\n" + "!" * 60)
        _say(" Could not install required packages: " + ", ".join(failed_req))
        _say(" Check your internet connection and run the app again.")
        _say("!" * 60)
        _wait_for_enter()
        sys.exit(1)
    if failed_opt:
        _say("\n Optional packages not installed (features disabled): " + ", ".join(failed_opt))
    try:
        with open(_STAMP, "w") as f:
            f.write(_stamp_value())
    except Exception:
        pass
    _say("\n Setup complete! Starting app...\n")


def bootstrap():
    if _is_android_early() or _is_packaged():
        return
    if sys.version_info < (3, 9):
        _say("Python 3.9 or newer is required. Please install the latest Python from python.org")
        _wait_for_enter()
        sys.exit(1)

    if not _in_our_venv():
        if not _ensure_venv():
            _say("\n Could not create the local environment (.venv).")
            _say(" On Linux install the 'python3-venv' package, then run again.")
            _wait_for_enter()
            sys.exit(1)
        py = _venv_python()
        _install_requirements(py)
        env = dict(os.environ)
        env["PYTHONNOUSERSITE"] = "1"
        sys.exit(subprocess.call([py, os.path.abspath(__file__)] + sys.argv[1:], env=env))

    _install_requirements(sys.executable)  # already inside the venv: just verify


bootstrap()

# --- 1. INSTANT CMD HIDER & PYGAME SILENCER (after bootstrap, so you can see the setup) ---
def _set_console_visible(visible):
    if os.name == 'nt':
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5 if visible else 0)
        except Exception:
            pass

_set_console_visible(False)
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
# ----------------------------------------------

import json
import math
import difflib
import random
import re
import bisect
import warnings
import traceback
import datetime
import time
import base64
import urllib.parse
import threading
import inspect
import asyncio
import hashlib
import http.server
import socketserver

import flet as ft
import requests

try:
    import flet_audio as fta
    from flet_audio import Audio
except Exception:
    fta = None
    Audio = getattr(ft, "Audio", None)

warnings.filterwarnings("ignore", category=DeprecationWarning)

APP_VERSION = "v10.0 (Universal: PC + Android APK)"

# --- 2. ERROR LOG IN APP FOLDER ---
BASE_APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(os.environ.get("FLET_APP_STORAGE_DATA") or BASE_APP_DIR, "error_log.txt")

def log_error(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] ERROR:\n{msg}\n{'-'*50}\n")
        print(f"CRASH LOGGED: {msg}")
    except Exception: pass

def global_exception_handler(exc_type, exc_value, exc_traceback):
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_error(f"FATAL SYSTEM CRASH:\n{err_msg}")
sys.excepthook = global_exception_handler

def thread_exception_handler(args):
    err_msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    log_error(f"THREAD CRASH ({getattr(args.thread, 'name', '?')}):\n{err_msg}")
threading.excepthook = thread_exception_handler
# ----------------------------------

# =========================================================
# UNIVERSAL FLET API HELPERS (Fixes Flet API changes)
# =========================================================
def make_border(width, color):
    try:
        if hasattr(ft, 'border') and hasattr(ft.border, 'all'):
            return ft.border.all(width, color)
        return ft.Border(
            top=ft.BorderSide(width, color), right=ft.BorderSide(width, color),
            bottom=ft.BorderSide(width, color), left=ft.BorderSide(width, color)
        )
    except Exception: return None

def make_padding(left=0, top=0, right=0, bottom=0, horizontal=None, vertical=None):
    l = horizontal if horizontal is not None else left
    r = horizontal if horizontal is not None else right
    t = vertical if vertical is not None else top
    b = vertical if vertical is not None else bottom

    try:
        if hasattr(ft, 'padding') and hasattr(ft.padding, 'only'):
            return ft.padding.only(left=l, top=t, right=r, bottom=b)
        return ft.Padding(left=l, top=t, right=r, bottom=b)
    except Exception: return l

def center_alignment():
    try: return ft.alignment.center
    except Exception:
        try: return ft.Alignment(0, 0)
        except Exception: return None

# =========================================================
# SAFE WRITABLE + PORTABLE DATA DIRECTORY
# Settings, favorites and audio cache live in
# "DailyDevotionalData" right beside this script.
# =========================================================
def get_safe_data_dir():
    app_folder = "DailyDevotionalData"
    packaged = os.environ.get("FLET_APP_STORAGE_DATA")   # Android / packaged app: persistent private storage
    if packaged:
        try:
            p = os.path.join(packaged, app_folder)
            os.makedirs(p, exist_ok=True)
            return p
        except Exception:
            pass
    portable = os.path.join(APP_DIR, app_folder)
    legacy_home = os.environ.get("HOME", os.path.expanduser("~"))
    if platform.system() == "Windows":
        legacy_home = os.environ.get("LOCALAPPDATA", legacy_home)
    legacy = os.path.join(legacy_home, app_folder)

    try:
        os.makedirs(portable, exist_ok=True)
        t = os.path.join(portable, ".test")
        with open(t, "w") as f: f.write("1")
        os.remove(t)
        # one-time migration of data from the old location
        if not os.path.exists(os.path.join(portable, "config.json")) and os.path.exists(os.path.join(legacy, "config.json")):
            try: shutil.copytree(legacy, portable, dirs_exist_ok=True)
            except Exception: pass
        return portable
    except Exception:  # read-only folder (e.g. Android) -> old behaviour
        try:
            os.makedirs(legacy, exist_ok=True)
            return legacy
        except Exception:
            import tempfile
            fb = os.path.join(tempfile.gettempdir(), app_folder)
            os.makedirs(fb, exist_ok=True)
            return fb

DATA_DIR = get_safe_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")

def is_android_sys():
    return _is_android_early()

# =========================================================
# ULTIMATE ANDROID FALLBACK: LOCALHOST STREAMING SERVER
# =========================================================
LOCAL_AUDIO_PORT = None

def start_local_server():
    global LOCAL_AUDIO_PORT
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=DATA_DIR, **kwargs)
        def log_message(self, format, *args): pass

    for port in range(8888, 8999):
        try:
            httpd = socketserver.TCPServer(("127.0.0.1", port), QuietHandler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            LOCAL_AUDIO_PORT = port
            break
        except Exception: continue

start_local_server()

# --- CROSS-PLATFORM AUDIO COMPATIBILITY ---
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# --- VIDEO RECORDING LIBRARIES (PC ONLY) ---
try:
    import mss
    import cv2
    import numpy as np
    import imageio_ffmpeg
    VIDEO_EXPORT_AVAILABLE = True
except ImportError:
    VIDEO_EXPORT_AVAILABLE = False

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

# =========================================================
# AUDIO ANALYSIS + TEXT<->AUDIO SYNC ENGINE
# =========================================================
def _hidden_startupinfo():
    if platform.system().lower() == "windows":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return si
    return None


def _silence_scan(exe, file_path, noise_db, min_d):
    cmd = [exe, "-hide_banner", "-i", file_path, "-af",
           f"silencedetect=noise={noise_db}dB:d={min_d}", "-f", "null", "-"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          startupinfo=_hidden_startupinfo(), errors="ignore")
    err = proc.stderr or ""
    duration = None
    m = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d+)", err)
    if m:
        h, mi, s = m.groups()
        duration = int(h) * 3600 + int(mi) * 60 + float(s)
    gaps, cur = [], None
    for line in err.splitlines():
        ms = re.search(r"silence_start: (-?[\d.]+)", line)
        me = re.search(r"silence_end: ([\d.]+)", line)
        if ms: cur = max(0.0, float(ms.group(1)))
        if me and cur is not None:
            gaps.append((cur, float(me.group(1))))
            cur = None
    if cur is not None and duration: gaps.append((cur, duration))
    return duration, gaps


def _quick_duration(path):
    """Duration without ffmpeg/pygame: WAV via wave, MP3 via frame bitrate (CBR)."""
    try:
        if os.path.splitext(path)[1].lower() == ".wav":
            import wave
            with wave.open(path, "rb") as w:
                return w.getnframes() / float(w.getframerate())
        total = os.path.getsize(path)
        with open(path, "rb") as f:
            hd = f.read(10)
            start = 0
            if hd[:3] == b"ID3" and len(hd) == 10:
                start = 10 + (((hd[6] & 0x7F) << 21) | ((hd[7] & 0x7F) << 14) | ((hd[8] & 0x7F) << 7) | (hd[9] & 0x7F))
            f.seek(start)
            buf = f.read(8192)
        br1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
        br2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
        for i in range(len(buf) - 4):
            if buf[i] == 0xFF and (buf[i + 1] & 0xE0) == 0xE0:
                ver, layer, bi = (buf[i + 1] >> 3) & 3, (buf[i + 1] >> 1) & 3, (buf[i + 2] >> 4) & 15
                if layer != 1 or not (0 < bi < 15):
                    continue
                if ver == 3: br = br1[bi]
                elif ver in (0, 2): br = br2[bi]
                else: continue
                return (total - start) * 8.0 / (br * 1000.0)
    except Exception:
        pass
    return None


def analyze_audio_timeline(file_path, fallback_text=""):
    """
    Returns dict(duration, speech_start, speech_end, gaps[(start,end)]).
    Scans at several silence thresholds and keeps the one whose number of
    gaps best fits the punctuation of the text.
    """
    fallback_dur = max(1.0, len(fallback_text) / 15.0)
    result = {"duration": fallback_dur, "speech_start": 0.0, "speech_end": fallback_dur, "gaps": []}
    if not file_path or not os.path.exists(file_path):
        return result

    target = len(re.findall(r"[.!?…,;:]", fallback_text)) + fallback_text.count("\n")
    best = None
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        for noise in (-48, -42, -36, -30):
            dur, g = _silence_scan(exe, file_path, noise, 0.14)
            if dur is None: continue
            inner = sum(1 for (a, b) in g if a > 0.08 and b < dur - 0.08)
            score = abs(inner - 0.8 * target)
            if best is None or score < best[0]:
                best = (score, dur, g)
    except Exception:
        best = None
    duration, gaps = (best[1], best[2]) if best else (None, [])

    if duration is None and PYGAME_AVAILABLE:
        try:
            if not pygame.mixer.get_init(): pygame.mixer.init()
            duration = pygame.mixer.Sound(file_path).get_length()
        except Exception: pass
    if duration is None:
        duration = _quick_duration(file_path)
    if duration is None:
        return result

    speech_start, speech_end, inner = 0.0, duration, []
    for (gs, ge) in sorted(gaps):
        if gs <= 0.08 and speech_start == 0.0: speech_start = ge
        elif ge >= duration - 0.08: speech_end = min(speech_end, gs)
        else: inner.append((gs, ge))
    if speech_end - speech_start < 0.5:
        speech_start, speech_end, inner = 0.0, duration, []
    return {"duration": duration, "speech_start": speech_start, "speech_end": speech_end, "gaps": inner}


def get_audio_duration(file_path, fallback_text):
    return analyze_audio_timeline(file_path, fallback_text)["duration"]


AUDIO_EXTS = (".mp3", ".wav", ".weba", ".webm", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".flac", ".mp4", ".3gp")


def find_cached_audio(folder, base):
    for ext in AUDIO_EXTS:
        p = os.path.join(folder, base + ext)
        if os.path.exists(p):
            return p
    return ""


def remove_cached_audio(folder, base):
    for ext in AUDIO_EXTS + (".align.json",):
        p = os.path.join(folder, base + ext)
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass


def _silent_wav_b64():
    """Tiny valid silent WAV: gives the Android Audio control a real source at startup."""
    import io, wave, struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 800)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def convert_to_playable(src, dest_dir, base_name):
    """Converts ANY audio/video file (.weba, .webm, .ogg, .m4a, .flac...) into a
    pygame-playable .mp3 (or .wav fallback) named base_name.*"""
    ext = os.path.splitext(src)[1].lower()
    remove_cached_audio(dest_dir, base_name)  # remove stale links first
    if is_android_sys():  # no ffmpeg on the phone: keep the file, Android's own player decodes it
        dest = os.path.join(dest_dir, base_name + (ext if ext in AUDIO_EXTS else ".mp3"))
        shutil.copy2(src, dest)
        return dest
    if ext == ".mp3":
        dest = os.path.join(dest_dir, base_name + ".mp3")
        shutil.copy2(src, dest)
        return dest
    if imageio_ffmpeg is None:
        raise Exception("imageio-ffmpeg is not installed, cannot convert this audio type.")
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    last_err = ""
    for out_ext, codec in ((".mp3", ["-c:a", "libmp3lame", "-q:a", "2"]), (".wav", ["-c:a", "pcm_s16le"])):
        dest = os.path.join(dest_dir, base_name + out_ext)
        cmd = [exe, "-y", "-i", src, "-vn", "-map", "0:a:0"] + codec + [dest]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=_hidden_startupinfo())
        if p.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 100:
            return dest
        last_err = p.stderr.decode("utf-8", errors="ignore")[-400:]
    raise Exception(f"Could not convert audio:\n{last_err}")


# =========================================================
# SMART WORD-LEVEL SYNC (faster-whisper forced alignment)
# Listens to the real audio, gets a timestamp for EVERY word,
# then matches those words to your text. Tempo-proof.
# =========================================================
try:
    WHISPER_AVAILABLE = importlib.util.find_spec("faster_whisper") is not None
except Exception:
    WHISPER_AVAILABLE = False

_WHISPER = {"name": None, "model": None}


def _norm_word(w):
    return re.sub(r"[\W_]+", "", (w or "").lower())


def reference_words(content):
    """Words in EXACTLY the same order build_reading_units() uses."""
    out = []
    for line in content.split("\n"):
        if line.strip():
            out.extend(line.split())
    return out


def align_words_to_reference(ref, hyp):
    """
    ref: list[str] words of the text.
    hyp: list[(word, start, end)] words heard in the audio.
    Returns list[(start, end)] for every ref word (or None if impossible).
    Misheard / merged / split / missing words are repaired by interpolation.
    """
    n = len(ref)
    if not n or not hyp:
        return None
    ref_n = [_norm_word(w) for w in ref]
    hyp_n = [_norm_word(h[0]) for h in hyp]
    ri = [i for i, x in enumerate(ref_n) if x]
    hi = [j for j, x in enumerate(hyp_n) if x]
    if not ri or not hi:
        return None
    a = [ref_n[i] for i in ri]
    b = [hyp_n[j] for j in hi]

    spans = [None] * n
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if i2 <= i1 or j2 <= j1:
            continue                               # nothing heard for these -> interpolate later
        if tag == "equal":
            for k in range(i2 - i1):
                h = hyp[hi[j1 + k]]
                spans[ri[i1 + k]] = (h[1], h[2])
        else:                                      # misheard/merged/split -> share the heard time span
            t0, t1 = hyp[hi[j1]][1], hyp[hi[j2 - 1]][2]
            lens = [max(1, len(a[i])) for i in range(i1, i2)]
            tot, cur = float(sum(lens)), t0
            for k, i in enumerate(range(i1, i2)):
                d = max(0.0, t1 - t0) * lens[k] / tot
                spans[ri[i]] = (cur, cur + d)
                cur += d

    i = 0
    while i < n:                                   # fill the remaining gaps
        if spans[i] is not None:
            i += 1
            continue
        j = i
        while j < n and spans[j] is None:
            j += 1
        chars = [max(1, len(ref[k])) for k in range(i, j)]
        est = 0.07 * sum(chars)
        prev_end = spans[i - 1][1] if i > 0 else None
        next_start = spans[j][0] if j < n else None
        if prev_end is None and next_start is None:
            return None
        if prev_end is None: prev_end = max(0.0, next_start - est)
        if next_start is None: next_start = prev_end + est
        if next_start < prev_end: next_start = prev_end
        tot, cur = float(sum(chars)), prev_end
        for k in range(i, j):
            d = (next_start - prev_end) * chars[k - i] / tot
            spans[k] = (cur, cur + d)
            cur += d
        i = j

    out, last = [], 0.0
    for s, e in spans:                             # enforce non-decreasing order
        s = max(s, last)
        out.append((s, max(e, s)))
        last = s
    return out


def _get_whisper(model_name, status_cb=None):
    if _WHISPER["model"] is not None and _WHISPER["name"] == model_name:
        return _WHISPER["model"]
    if status_cb:
        status_cb(f"⬇️ Loading '{model_name}' speech model (first time downloads it, please wait)...")
    from faster_whisper import WhisperModel
    root = os.path.join(DATA_DIR, "whisper_models")   # inside the app folder = portable
    os.makedirs(root, exist_ok=True)
    m = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=root)
    _WHISPER["name"], _WHISPER["model"] = model_name, m
    return m


def _local_whisper_hyp(audio_path, content, model_name, status_cb=None):
    model = _get_whisper(model_name, status_cb)
    if status_cb:
        status_cb("🧠 Analyzing voice timing word-by-word (one time only)...")
    segments, _info = model.transcribe(
        audio_path, word_timestamps=True, beam_size=5, vad_filter=False,
        condition_on_previous_text=False, initial_prompt=content[:220])
    hyp = []
    for seg in segments:
        for w in (getattr(seg, "words", None) or []):
            if w.start is not None and w.end is not None:
                hyp.append((w.word, float(w.start), float(w.end)))
    return hyp


def parse_groq_words(data):
    hyp = []
    def _add(w):
        try:
            hyp.append((str(w.get("word", "")), float(w["start"]), float(w["end"])))
        except Exception:
            pass
    for w in (data.get("words") or []):
        _add(w)
    if not hyp:
        for seg in (data.get("segments") or []):
            for w in (seg.get("words") or []):
                _add(w)
    return hyp


def _cloud_whisper_hyp(audio_path, keys, status_cb=None):
    """Word timestamps from Groq's hosted Whisper (works on Android: no heavy install)."""
    if not keys:
        raise Exception("no Groq API key saved")
    if os.path.getsize(audio_path) > 24 * 1024 * 1024:
        raise Exception("audio is larger than the 24 MB cloud limit")
    if status_cb:
        status_cb("☁️ Analyzing voice timing in the cloud (Groq Whisper, one time only)...")
    name = os.path.basename(audio_path)
    if name.lower().endswith(".weba"):
        name = name[:-5] + ".webm"
    last = "unknown error"
    for k in keys:
        try:
            with open(audio_path, "rb") as f:
                r = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {k.strip()}"},
                    files={"file": (name, f)},
                    data={"model": "whisper-large-v3-turbo", "response_format": "verbose_json",
                          "timestamp_granularities[]": "word", "temperature": "0"},
                    timeout=180)
            if r.status_code == 200:
                hyp = parse_groq_words(r.json())
                if hyp:
                    return hyp
                last = "response had no word timestamps"
            else:
                last = f"{r.status_code}: {r.text[:200]}"
        except Exception as e:
            last = str(e)
    raise Exception(f"Groq transcription failed: {last}")


def smart_word_times(audio_path, content, engine="Auto", model_name="base", cache_path=None, status_cb=None, groq_keys=None):
    """
    Per-word (start, end) for the text, or None.
    Order: disk cache -> local Whisper (PC) -> cloud Whisper (Groq). Result is cached,
    so a file analyzed on the PC also works on the phone when the cache folder is copied.
    """
    if not audio_path or not os.path.exists(audio_path):
        return None
    ref = reference_words(content)
    if not ref:
        return None
    eng = engine or "Auto"
    key = _hl.md5(f"{content}|{os.path.getsize(audio_path)}".encode("utf-8")).hexdigest()
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("key") == key and len(d.get("times", [])) == len(ref):
                return [tuple(x) for x in d["times"]]
        except Exception:
            pass
    if eng.startswith("Classic"):
        return None

    if eng.startswith("Local"): order = ["local"]
    elif eng.startswith("Cloud"): order = ["cloud"]
    else: order = ["local", "cloud"]

    errors = []
    for kind in order:
        try:
            if kind == "local":
                if not WHISPER_AVAILABLE:
                    continue
                hyp = _local_whisper_hyp(audio_path, content, model_name, status_cb)
            else:
                if not groq_keys:
                    continue
                hyp = _cloud_whisper_hyp(audio_path, groq_keys, status_cb)
            times = align_words_to_reference(ref, hyp)
            if times:
                if cache_path:
                    try:
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump({"key": key, "times": times}, f)
                    except Exception:
                        pass
                return times
        except Exception as e:
            errors.append(f"{kind}: {e}")
            log_error(f"Smart sync ({kind}) failed: {e}")
    if errors:
        raise Exception("; ".join(errors))
    return None


class WordSync:
    """Exact word-level clock: time -> which chunk is being spoken."""
    def __init__(self, unit_first_word, word_times):
        last_i = len(word_times) - 1
        self.starts, last = [], 0.0
        for w in unit_first_word:
            s = max(word_times[min(w, last_i)][0], last)
            self.starts.append(s)
            last = s

    def unit_at(self, t):
        return max(0, bisect.bisect_right(self.starts, t) - 1)


class SyncMap:
    """Aligns text pause points (. , ; :) to real audio gaps with a global DP, tempo-tolerant."""
    def __init__(self, units, duration, speech_start, speech_end, gaps):
        self.n = len(units)
        self.cum, total = [], 0.0
        for u in units:
            total += max(0.5, u["w"])
            self.cum.append(total)
        self.total = max(total, 1.0)
        ss, se = speech_start, max(speech_end, speech_start + 0.5)
        self.ss, self.se = ss, se
        rate = (se - ss) / self.total

        pts = []  # (weight where speech stops, weight where next speech starts, strength)
        for i, u in enumerate(units):
            if i >= self.n - 1 or u["last_pause"] <= 0: continue
            pts.append((self.cum[i] - u["last_pause"], self.cum[i], u["last_pause"]))
        gaps = sorted((gs, min(ge, se)) for gs, ge in gaps if gs > ss - 0.05 and ge < se + 0.05)

        wpos, tpos = [0.0], [ss]
        try:
            matches = self._align(pts, gaps, ss, se, rate)
        except Exception:
            matches = []
        for pi, gi in matches:
            sw, ew, _ = pts[pi]
            gs, ge = gaps[gi]
            if sw >= wpos[-1] and gs >= tpos[-1]:
                wpos.append(sw); tpos.append(gs)
                if ew >= wpos[-1] and ge >= tpos[-1]:
                    wpos.append(ew); tpos.append(ge)
        wpos.append(self.total); tpos.append(se)
        self.wpos, self.tpos = wpos, tpos

    def _align(self, pts, gaps, ss, se, rate):
        P, G = len(pts), len(gaps)
        if not P or not G: return []
        SKIP_PT, SKIP_GAP, CAP, MAXI, MAXJ = 0.35, 0.25, 1.2, 6, 8
        gstarts = [g[0] for g in gaps]
        total = self.total

        def segcost(w0, t0, i, j):
            exp = (pts[i][0] - w0) * (se - t0) / max(total - w0, 1e-6)  # remaining-time rate
            act = gaps[j][0] - t0
            if exp < 0.05 or act < 0.02: return CAP
            return min(math.log(act / exp) ** 2, CAP)

        best = {}
        for i in range(P):
            exp_t = ss + pts[i][0] * rate
            tol = 1.5 + 0.35 * (exp_t - ss)
            lo = bisect.bisect_left(gstarts, exp_t - tol)
            hi = bisect.bisect_right(gstarts, exp_t + tol)
            for j in range(lo, hi):
                glen = gaps[j][1] - gaps[j][0]
                bonus = 0.4 * min(glen, 0.8) * pts[i][2] / 7.0
                cands = [(SKIP_PT * i + SKIP_GAP * 0.5 * j + segcost(0.0, ss, i, j), None)]
                for i0 in range(max(0, i - MAXI), i):
                    for j0 in range(max(0, j - MAXJ), j):
                        prev = best.get((i0, j0))
                        if prev is None: continue
                        c = (prev[0] + SKIP_PT * (i - i0 - 1) + SKIP_GAP * (j - j0 - 1)
                             + segcost(pts[i0][1], gaps[j0][1], i, j))
                        cands.append((c, (i0, j0)))
                c, p = min(cands, key=lambda x: x[0])
                best[(i, j)] = (c - bonus, p)

        bk, bc = None, SKIP_PT * P  # must beat "match nothing"
        for (i, j), (c, _) in best.items():
            tot = c + SKIP_PT * (P - 1 - i) + 0.05 * (G - 1 - j)
            if tot < bc: bk, bc = (i, j), tot
        out = []
        while bk is not None:
            out.append(bk)
            bk = best[bk][1]
        out.reverse()
        return out

    def unit_at(self, t):
        if t <= self.tpos[0]: return 0
        if t >= self.tpos[-1]: return self.n - 1
        j = max(0, min(bisect.bisect_right(self.tpos, t) - 1, len(self.tpos) - 2))
        t0, t1, w0, w1 = self.tpos[j], self.tpos[j + 1], self.wpos[j], self.wpos[j + 1]
        w = w0 if t1 <= t0 else w0 + (t - t0) / (t1 - t0) * (w1 - w0)
        return max(0, min(bisect.bisect_right(self.cum, w), self.n - 1))


def get_length_instruction(length_str):
    if "Short" in length_str: return "VERY SHORT body (strictly 1 paragraph, maximum of 3 to 4 sentences, keep it concise)"
    elif "Medium" in length_str: return "medium body (strictly 2 paragraphs)"
    elif "Long" in length_str: return "long body (3 to 4 paragraphs)"
    else: return "in-depth body (5 or more paragraphs)"

def short_lang(lang):
    if lang == "Taglish": return "authentic conversational Filipino Taglish"
    if lang == "Conyo": return "stereotypical preppy Filipino 'conyo' speak"
    return lang

# ==========================================
# 2. BACKEND LOGIC (GROQ, GEMINI, OPENAI, LM STUDIO)
# ==========================================
_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)

def clean_ai_text(t):
    """Removes hidden reasoning blocks some models leak into the reply."""
    return _THINK_RE.sub("", t or "").strip()


def normalize_9router_base(base):
    """'192.168.1.5:20128' / 'http://host:20128' / '.../v1' -> 'http://host:20128/v1'"""
    b = (base or "").strip().rstrip("/")
    if not b:
        b = "http://localhost:20128/v1"
    if not b.lower().startswith("http"):
        b = "http://" + b
    if b.endswith("/chat/completions"):
        b = b[:-len("/chat/completions")]
    if not b.endswith("/v1"):
        b += "/v1"
    return b


# ---------------------------------------------------------
# MODEL HEALTH: live testing, discovery and auto-heal helpers
# ---------------------------------------------------------
_SKIP_WORDS = ("whisper", "tts", "guard", "embed", "image", "imagen", "dall", "audio", "realtime", "transcribe",
               "moderation", "rerank", "safeguard", "sora", "veo", "lyria", "robotics", "computer-use", "-live",
               "omni", "deep-research", "antigravity", "banana", "orpheus", "playai", "search")
_COSTLY_WORDS = ("opus", "fable", "argon", "-pro", "gpt-5.5")          # never auto-picked by auto-heal
_PREFER = ("flash-lite", "lite", "nano", "mini", "haiku", "20b", "flash", "sonnet", "oss", "claude", "glm", "qwen")


def is_costly_model(m):
    return any(w in (m or "").lower() for w in _COSTLY_WORDS)


def is_chat_model_id(m):
    low = (m or "").lower()
    return bool(low) and not any(w in low for w in _SKIP_WORDS)


def _model_rank(m):
    low = (m or "").lower()
    for i, w in enumerate(_PREFER):
        if w in low:
            return i
    return len(_PREFER)


def classify_failure(status, text):
    """-> 'auth' | 'exhausted' | 'dead' | 'down'"""
    low = (text or "").lower()
    if status in (401, 403) or any(w in low for w in ("invalid api key", "incorrect api key", "invalid x-api-key", "unauthorized")):
        return "auth"
    if status == 429 or any(w in low for w in ("exhaust", "quota", "rate limit", "insufficient", "credit", "limit reached", "too many requests", "billing")):
        return "exhausted"
    if status in (400, 404, 410) or any(w in low for w in ("decommission", "deprecat", "no longer available", "not found", "does not exist", "unknown model", "unsupported", "invalid model", "retired", "no available", "not supported")):
        return "dead"
    return "down"


def _base_from_endpoint(endpoint):
    e = (endpoint or "").rstrip("/")
    return e[:-len("/chat/completions")] if e.endswith("/chat/completions") else e


def discover_models(kind, key, endpoint=None, timeout=12):
    """Live list of chat-capable model ids from the provider ([] on any failure)."""
    try:
        key = (key or "").strip()
        if kind == "groq":
            url, h = "https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"}
        elif kind == "openai":
            url, h = "https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"}
        elif kind == "gemini":
            url, h = f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key={key}", {}
        elif kind == "claude":
            url, h = "https://api.anthropic.com/v1/models?limit=100", {"x-api-key": key, "anthropic-version": "2023-06-01"}
        elif kind in ("ninerouter", "lmstudio"):
            url = _base_from_endpoint(endpoint) + "/models"
            h = {"Authorization": f"Bearer {key}"} if key else {}
        else:
            return []
        r = requests.get(url, headers=h, timeout=timeout)
        if r.status_code != 200:
            return []
        d = r.json()
        ids = []
        if kind == "gemini":
            for m in d.get("models", []):
                if "generateContent" in (m.get("supportedGenerationMethods") or []):
                    ids.append((m.get("name") or "").replace("models/", ""))
            ids = [i for i in ids if i.startswith("gemini")]
        else:
            for m in d.get("data", []):
                if m.get("active") is False:
                    continue
                ids.append(m.get("id"))
        if kind == "openai":
            ids = [i for i in ids if i and i.startswith(("gpt-", "chatgpt"))]
        out = []
        for i in ids:
            if i and i not in out and is_chat_model_id(i):
                out.append(i)
        return sorted(out, key=_model_rank)
    except Exception:
        return []


def probe_chat_model(kind, model, key, endpoint=None, timeout=25):
    """One tiny request. -> (status, seconds, detail); status in ok|exhausted|dead|auth|down|net"""
    t0 = time.time()
    msg = [{"role": "user", "content": "Reply with the single word: OK"}]
    try:
        key = (key or "").strip()
        if kind == "gemini":
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                              json={"contents": [{"role": "user", "parts": [{"text": msg[0]["content"]}]}],
                                    "generationConfig": {"maxOutputTokens": 64}}, timeout=timeout)
        elif kind == "claude":
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                              json={"model": model, "max_tokens": 16, "messages": msg}, timeout=timeout)
        else:
            headers = {"Content-Type": "application/json"}
            if key and kind != "lmstudio":
                headers["Authorization"] = f"Bearer {key}"
            newstyle = model.lower().split("/")[-1].startswith(("gpt-5", "o1", "o3", "o4"))
            body = {"model": model, "messages": msg, ("max_completion_tokens" if newstyle else "max_tokens"): (64 if newstyle else 16)}
            r = requests.post(endpoint, headers=headers, json=body, timeout=timeout)
            if r.status_code == 400 and ("max_tokens" in r.text or "max_completion_tokens" in r.text):
                body.pop("max_completion_tokens", None); body.pop("max_tokens", None)
                body["max_tokens" if newstyle else "max_completion_tokens"] = 64
                r = requests.post(endpoint, headers=headers, json=body, timeout=timeout)
        dt = time.time() - t0
        if r.status_code == 200:
            return "ok", dt, ""
        return classify_failure(r.status_code, r.text), dt, r.text[:160]
    except requests.exceptions.Timeout:
        return "down", time.time() - t0, "timed out"
    except Exception as e:
        return "net", time.time() - t0, str(e)[:160]


def probe_many(kind, models, key, endpoint=None, workers=4, progress=None):
    """Tests models in parallel. -> (good[(model, secs)] fastest first, bad{model: (status, detail)})"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    good, bad, done = [], {}, 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(probe_chat_model, kind, m, key, endpoint, 30 if kind == "ninerouter" else 25): m for m in models}
        for f in as_completed(futs):
            m = futs[f]
            try:
                st, dt, det = f.result()
            except Exception as e:
                st, dt, det = "net", 0.0, str(e)
            done += 1
            if st == "ok": good.append((m, dt))
            else: bad[m] = (st, det)
            if progress:
                try: progress(done, len(models), len(good))
                except Exception: pass
    good.sort(key=lambda x: (is_costly_model(x[0]), x[1]))
    return good, bad


class BaseBackend:
    def __init__(self, config_file, service_name):
        self.config_file = config_file
        self.service_name = service_name
        self.keys = self.load_keys()
        self.key_index = 0
        self.kind = service_name
        self.heal_pool = None      # known-good models set by the app
        self.auto_heal = True
        self.healed_to = None      # set when auto-heal switched model
        self.timeout_override = None

    def load_keys(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    return data.get(f"{self.service_name}_keys", [])
            except json.JSONDecodeError: return []
        return []

    def save_keys(self, keys):
        self.keys = keys
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
            except json.JSONDecodeError: pass
        data[f"{self.service_name}_keys"] = self.keys
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            log_error(f"Failed to save keys: {e}")

    def _first_key(self):
        return self.keys[0].strip() if self.keys else ""

    def _is_model_problem(self, text):
        """True when switching to ANOTHER model could fix the failure (retired / exhausted / overloaded)."""
        low = (text or "").lower()
        if any(w in low for w in ("invalid api key", "incorrect api key", "invalid x-api-key", "unauthorized",
                                  "no api keys found", "no claude api keys", "could not connect", "authentication")):
            return False
        hints = ("decommission", "deprecat", "no longer available", "not found", "does not exist", "model_not_found",
                 "unknown model", "unsupported model", "invalid model", "retired", "exhaust", "quota", "rate limit",
                 "(429)", "status 429", "insufficient", "credit", "overloaded", "capacity", "empty reply",
                 "no available", "not supported", "status 404", "status 5")
        if self.kind == "ninerouter":
            hints += ("timed out", "status 400")
        return any(w in low for w in hints)

    def _send_request(self, prompt, model, temperature=0.95):
        """Sends the request; if the model is retired/exhausted, auto-heals to a working one."""
        self.healed_to = None
        ok, res = self._raw_send(prompt, model, temperature)
        if ok or not self.auto_heal or not self._is_model_problem(res):
            return ok, res
        tried = [model]

        def try_list(cands, limit):
            for alt in cands:
                if limit <= 0: break
                if alt in tried or (is_costly_model(alt) and not is_costly_model(model)):
                    continue
                limit -= 1
                tried.append(alt)
                self.timeout_override = 60
                try:
                    ok2, res2 = self._raw_send(prompt, alt, temperature)
                finally:
                    self.timeout_override = None
                if ok2:
                    self.healed_to = alt
                    return ok2, res2
                if not self._is_model_problem(res2):
                    return False, res2
            return None

        r = try_list(list(self.heal_pool or []), 5)
        if r: return r
        try:
            live = discover_models(self.kind, self._first_key(), getattr(self, "endpoint", None))
        except Exception:
            live = []
        r = try_list(live, 4)
        if r: return r
        return False, (f"{res}\n\nAuto-heal also tried: {', '.join(tried[1:]) or 'nothing available'} - none worked.\n"
                       "Press '🩺 Test & Fix Models' in Setup to find models that work right now.")

    def _raw_send(self, prompt, model, temperature=0.95):
        raise NotImplementedError

    # ---------- shared high-level actions (same for every provider) ----------
    def generate_devotional(self, style, version, theme, length, lang, custom_inst, model, duration="1 Day", format_type="Standard Devotional"):
        try: num_days = int(duration.split()[0])
        except: num_days = 1
        prompt = self._build_base_prompt(version, theme, custom_inst, num_days, format_type) + self._build_format_prompt(style, length, lang, num_days, format_type)
        return self._send_request(prompt, model, temperature=0.95)

    def revise_reflection(self, full_content, style, length, lang, custom_inst, model, format_type="Standard Devotional"):
        lang_instruction = short_lang(lang)
        length_inst = get_length_instruction(length)
        prompt = (
            "You are an inspiring Christian guide.\n"
            f"Please rewrite ONLY the main body/reflection portion(s) of the following {format_type}. "
            f"Carefully adopt a '{style}' tone and provide {length_inst} for each section. "
            f"The ENTIRE output MUST be written in {lang_instruction}.\n\n"
        )
        if custom_inst: prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_inst}\n\n"
        prompt += (
            "CRITICAL: Keep all structural headers exactly the same. Only change the content text. "
            "Output the full, updated document preserving all original formatting and separators.\n\n"
            f"CONTENT TO REVISE:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.8)

    def revise_verse(self, full_content, target_version, model, format_type="Standard Devotional"):
        prompt = (
            "You are a helpful Christian Bible scholar. "
            f"Please update ALL Bible verses in the following {format_type} to use ONLY the '{target_version}' translation.\n\n"
            "CRITICAL: Keep all reflection and structural headers exactly the same. Only change the Verse text and reference. "
            "Output the full, updated document preserving all original formatting and separators.\n\n"
            f"CONTENT TO REVISE:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.7)

    def generate_qa(self, full_content, lang, custom_inst, model, format_type="Standard Devotional"):
        lang_instruction = short_lang(lang)
        prompt = (
            "You are an inspiring Christian guide.\n"
            f"Based on the following {format_type}, generate 2 to 3 thoughtful reflection questions and their suggested answers.\n"
            f"The ENTIRE output MUST be written in {lang_instruction}.\n\n"
        )
        if custom_inst: prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_inst}\n\n"
        prompt += (
            "CRITICAL: Format your output cleanly with 'Question 1:', 'Answer:', etc. "
            "Output ONLY the questions and answers. Do not repeat the original document.\n\n"
            f"CONTENT:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.7)

    def _build_base_prompt(self, bible_version, theme, custom_instruction, num_days=1, format_type="Standard Devotional"):
        seed_id = random.randint(100000, 999999)
        plural = "s" if num_days > 1 else ""

        if format_type == "Standard Devotional": item_name = "everyday Bible devotional"
        elif format_type == "Sermon Outline": item_name = "Sermon Outline"
        elif format_type == "Bible Study Guide": item_name = "Bible Study Guide"
        elif format_type == "Short Story / Parable": item_name = "Christian short story / parable"
        elif format_type == "Poem": item_name = "inspiring Christian poem"
        elif format_type == "Prayer Focus": item_name = "guided prayer session"
        elif format_type == "S.O.A.P. Method": item_name = "S.O.A.P. Bible study"
        elif format_type == "Understanding Format": item_name = "practical 'Understanding' devotional"
        elif format_type == "Declarative Style": item_name = "declarative truth devotion"
        elif format_type == "Journaling / Brain-Dump": item_name = "journaling / brain-dump session"
        elif format_type == "One-Verse Breath Focus": item_name = "one-verse breath focus"
        elif format_type == "Three-Part Devotional": item_name = "three-part practical devotional"
        elif format_type == "Realtalk Devotional": item_name = "'Realtalk' devotional"
        else: item_name = format_type

        base_prompt = f"[SYSTEM UNIQUE ID: {seed_id}]\nYou are a highly creative Christian guide. Generate {num_days} distinct {item_name}{plural} using the '{bible_version}' translation.\n"

        if custom_instruction:
            base_prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_instruction}\nCRITICAL: Choose completely unique Bible verses that fit this instruction. DO NOT repeat verses across days.\n\n"
        else:
            if theme.lower() == "random":
                themes = ["hope", "faith", "God's love", "courage", "patience", "forgiveness", "joy", "peace", "grace", "mercy", "strength", "healing", "trusting God", "wisdom", "compassion", "humility", "perseverance", "gratitude", "kindness", "obedience", "overcoming fear", "guidance", "comfort in sorrow", "God's promises", "light in darkness", "fellowship", "worship", "praising God", "The Holy Spirit", "creation", "redemption", "serving Others"]
                selected_theme = random.choice(themes)
                base_prompt += f"Focus all content on the theme of '{selected_theme}'. CRITICAL INSTRUCTION: You MUST select unique verses for each day. Try selecting from different books of the Bible. DO NOT use commonly quoted verses like John 3:16, Jeremiah 29:11, Proverbs 3:5-6, or Philippians 4:13. Find hidden gems.\n\n"
            else:
                base_prompt += f"Focus all content on the theme of '{theme}'. CRITICAL INSTRUCTION: You MUST select completely unique verses for each day. DO NOT use the most commonly quoted verses. Dig deep for unique scriptures.\n\n"
        return base_prompt

    def _build_format_prompt(self, reflection_style, reflection_length, language, num_days=1, format_type="Standard Devotional"):
        lang_instruction = language
        if language == "Taglish":
            lang_instruction = (
                "authentic, conversational Filipino Taglish. "
                "CRITICAL LANGUAGE RULES: "
                "1. Speak like a modern Pinoy Christian (mix English and everyday Tagalog naturally). "
                "2. STRICTLY FORBIDDEN: Do not use deep, archaic, or formal Tagalog words (e.g., 'saklaw', 'datapwat', 'subalit', 'sapagkat'). "
                "3. If a Tagalog word feels too deep or formal, you MUST use the English word instead. "
                "4. Use warm, everyday terms like 'kapatid', 'Lord', 'Panginoon', and 'blessings'."
            )
        elif language == "Modern Tagalog":
            lang_instruction = (
                "authentic, conversational Tagalog. "
                "CRITICAL LANGUAGE RULES: "
                "1. Write in clear, modern, everyday Tagalog. Do not heavily mix with English like Taglish, but keep it completely natural. "
                "2. STRICTLY FORBIDDEN: Do not use deep, archaic, or formal dictionary Tagalog words (e.g., 'saklaw', 'datapwat', 'subalit', 'sapagkat', 'ngunit'). "
                "3. If a Tagalog word is too deep or poetic, use a simpler everyday Tagalog equivalent. "
                "4. Keep the tone warm and respectful, using terms like 'kapatid', 'Panginoon', and 'biyaya'."
            )
        elif language == "Conyo":
            lang_instruction = "stereotypical preppy Filipino 'conyo' speak (speak like a wealthy, preppy modern Pinoy Christian. Heavily mix English and Tagalog in a stereotypical 'conyo' accent. Use phrases like 'make pray', 'so blessed', 'super nice', 'like', 'literally', 'oh my gosh', 'yah', 'diba'. Keep it respectful but undeniably conyo.)"

        length_inst = get_length_instruction(reflection_length)
        dates = [(datetime.datetime.now() + datetime.timedelta(days=i)).strftime("%A, %B %d, %Y") for i in range(num_days)]
        format_str = f"For the output, carefully adopt a '{reflection_style}' tone and delivery style. The ENTIRE output MUST be written in {lang_instruction}.\n\n"

        if format_type == "Standard Devotional":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using these exact headers: 'Date:', 'Verse:', 'Reflection:', and 'Prayer:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Verse:\n[Insert EXACTLY ONE Bible Verse and Reference Here]\n\n"
                f"Reflection:\n[Insert a {length_inst} here matching the requested style]\n\n"
                "Prayer:\n[Insert a short prayer here]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} devotionals. For EACH day, use these exact headers: 'Date:', 'Verse:', 'Reflection:', and 'Prayer:'. Separate each day with a divider line (---).\n"
        elif format_type == "Realtalk Devotional":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using these exact headers: 'Date:', 'Realtalk Verse:', 'The Realtalk:', 'The Challenge:', and 'Short Prayer:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Realtalk Verse:\n[Insert EXACTLY ONE Bible Verse and Reference Here]\n\n"
                f"The Realtalk:\n[Speak honestly and directly, like a real friend, about a real-life struggle connected to the verse. Provide a {length_inst} here]\n\n"
                "The Challenge:\n[Give one small, practical challenge for today]\n\n"
                "Short Prayer:\n[Insert a short, honest prayer here]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Realtalk devotionals. For EACH day, use headers: 'Date:', 'Realtalk Verse:', 'The Realtalk:', 'The Challenge:', 'Short Prayer:'. Separate each day with a divider line (---).\n"
        elif format_type == "Sermon Outline":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide a Sermon Outline using these exact headers: 'Date:', 'Title:', 'Main Text:', 'Introduction:', 'Key Points:', and 'Conclusion:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Title:\n[Insert Catchy Sermon Title]\n\n"
                "Main Text:\n[Insert the core Bible verse(s)]\n\n"
                f"Introduction:\n[Insert a short intro]\n\n"
                f"Key Points:\n[Provide 3-4 key points with brief explanations, length should be roughly {length_inst}]\n\n"
                "Conclusion:\n[Insert a powerful closing]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Sermon Outlines. For EACH day, use headers: 'Date:', 'Title:', 'Main Text:', 'Introduction:', 'Key Points:', and 'Conclusion:'. Separate each day with a divider line (---).\n"
        elif format_type == "Bible Study Guide":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide a Bible Study Guide using these exact headers: 'Date:', 'Passage:', 'Context & Background:', 'Observation Questions:', and 'Application Questions:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Passage:\n[Insert Bible Passage]\n\n"
                f"Context & Background:\n[Explain the historical/biblical context briefly]\n\n"
                f"Observation Questions:\n[List 2-3 questions about the text]\n\n"
                f"Application Questions:\n[List 2-3 questions for personal reflection]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Bible Study Guides. For EACH day, use headers: 'Date:', 'Passage:', 'Context & Background:', 'Observation Questions:', 'Application Questions:'. Separate each day with a divider line (---).\n"
        elif format_type == "Short Story / Parable":
            format_rules = (
                "CRITICAL FORMATTING RULE: Write a modern Christian short story or parable illustrating the theme using these exact headers: 'Date:', 'Story Title:', 'Inspired By Verse:', and 'Story:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Story Title:\n[Insert Story Title]\n\n"
                "Inspired By Verse:\n[Insert the foundational Bible Verse]\n\n"
                f"Story:\n[Write a {length_inst} engaging short story illustrating the verse's meaning]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Short Stories. For EACH day, use headers: 'Date:', 'Story Title:', 'Inspired By Verse:', and 'Story:'. Separate each day with a divider line (---).\n"
        elif format_type == "Poem":
            format_rules = (
                "CRITICAL FORMATTING RULE: Write an inspiring Christian poem based on the verse/theme using these exact headers: 'Date:', 'Poem Title:', 'Scripture Inspiration:', and 'Poem:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Poem Title:\n[Insert Poem Title]\n\n"
                "Scripture Inspiration:\n[Insert the foundational Bible Verse]\n\n"
                f"Poem:\n[Write a touching, rhyming poem]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Poems. For EACH day, use headers: 'Date:', 'Poem Title:', 'Scripture Inspiration:', and 'Poem:'. Separate each day with a divider line (---).\n"
        elif format_type == "Prayer Focus":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide a deep, guided prayer session using these exact headers: 'Date:', 'Focus Verse:', 'Adoration:', 'Confession:', 'Thanksgiving:', and 'Supplication:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Focus Verse:\n[Insert Bible Verse]\n\n"
                "Adoration:\n[Praising God for who He is]\n\n"
                "Confession:\n[Acknowledging our shortcomings]\n\n"
                "Thanksgiving:\n[Thanking God for His blessings]\n\n"
                "Supplication:\n[Presenting requests to God]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Prayer Focus sessions. For EACH day, use headers: 'Date:', 'Focus Verse:', 'Adoration:', 'Confession:', 'Thanksgiving:', 'Supplication:'. Separate each day with a divider line (---).\n"
        elif format_type == "S.O.A.P. Method":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using the S.O.A.P. method with these exact headers: 'Date:', 'S - Scripture:', 'O - Observation:', 'A - Application:', and 'P - Prayer:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "S - Scripture:\n[Insert EXACTLY ONE Bible Verse and Reference Here]\n\n"
                "O - Observation:\n[What is happening in this verse? What is the main message?]\n\n"
                f"A - Application:\n[How does this apply to life today? Provide a {length_inst} here]\n\n"
                "P - Prayer:\n[Write a short prayer asking God to help apply this truth]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} S.O.A.P. devotionals. For EACH day, use headers: 'Date:', 'S - Scripture:', 'O - Observation:', 'A - Application:', 'P - Prayer:'. Separate each day with a divider line (---).\n"
        elif format_type == "Understanding Format":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using these exact headers: 'Date:', 'The Verse:', 'The Understanding:', 'The Reflection:', and 'The Prayer:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "The Verse:\n[Insert EXACTLY ONE Bible Verse and Reference Here]\n\n"
                "The Understanding:\n[Break down what the verse actually means in plain English]\n\n"
                f"The Reflection:\n[Connect the meaning to an everyday struggle. Provide a {length_inst} here]\n\n"
                "The Prayer:\n[End with a targeted prayer surrendering that specific struggle to God]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} devotionals. For EACH day, use headers: 'Date:', 'The Verse:', 'The Understanding:', 'The Reflection:', 'The Prayer:'. Separate each day with a divider line (---).\n"
        elif format_type == "Declarative Style":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE declarative devotion using these exact headers: 'Date:', 'Focus Promise:', and 'Declaration:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Focus Promise:\n[Insert EXACTLY ONE Bible Verse containing a promise here]\n\n"
                f"Declaration:\n[Write out a powerful, first-person declaration speaking this truth over the day. No deep study, just speaking truth. Length: {length_inst}]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} declarative devotions. For EACH day, use headers: 'Date:', 'Focus Promise:', 'Declaration:'. Separate each day with a divider line (---).\n"
        elif format_type == "Journaling / Brain-Dump":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE journaling devotion using these exact headers: 'Date:', 'The Brain-Dump:', 'The Anchor Verse:', and 'The Exchange:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "The Brain-Dump:\n[Identify a relatable modern stressor, worry, or heavy thought as if dumping it on a page]\n\n"
                "The Anchor Verse:\n[Insert EXACTLY ONE comforting Bible Verse here]\n\n"
                f"The Exchange:\n[Write how God's truth directly answers the worries dumped above. Length: {length_inst}]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} journaling devotions. For EACH day, use headers: 'Date:', 'The Brain-Dump:', 'The Anchor Verse:', 'The Exchange:'. Separate each day with a divider line (---).\n"
        elif format_type == "One-Verse Breath Focus":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE breath focus devotion using these exact headers: 'Date:', 'Breath Verse:', and 'Actionable Focus:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Breath Verse:\n[Insert ONE VERY SHORT Bible Verse here, e.g. Psalm 46:10]\n\n"
                f"Actionable Focus:\n[Provide a short, easy-to-remember focus or mantra for the day. {length_inst}]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} breath focus devotions. For EACH day, use headers: 'Date:', 'Breath Verse:', 'Actionable Focus:'. Separate each day with a divider line (---).\n"
        elif format_type == "Three-Part Devotional":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using the exact structure below. Do NOT use headers like 'Date:', 'Reflection:', or 'Prayer:'. Do NOT use bolding or asterisks.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                "[Insert Bible Reference Here]\n"
                '"[Insert Bible Verse Text Here]"\n\n'
                "[Paragraph 1: The Struggle - Describe a specific, relatable modern struggle. DO NOT use repetitive intros like 'It is really easy sometimes...' Jump straight into the scenario.]\n\n"
                "[Paragraph 2: The Solution - Explain how the biblical truth directly counters this struggle.]\n\n"
                "[Paragraph 3: The Application - Give a practical mindset shift for the day.]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Three-Part Devotionals. For EACH day, output ONLY the verse and 3 paragraphs. NO headers like 'Date:' or 'Reflection:'. Separate each day with a divider line (---).\n"
        else:
            format_rules = ""
            multi_format_rules = ""

        if num_days == 1: format_str += format_rules
        else: format_str += multi_format_rules + "\nAssigned Dates to use in order:\n" + "\n".join(dates)
        return format_str

class OpenAICompatibleBackend(BaseBackend):
    KEYLESS = ("lmstudio", "ninerouter")           # these work without an API key

    def __init__(self, config_file, service_name, endpoint):
        super().__init__(config_file, service_name)
        self.endpoint = endpoint

    @staticmethod
    def _no_temperature(model):
        m = (model or "").lower().split("/")[-1]
        return m.startswith(("gpt-5", "o1", "o3", "o4"))   # reasoning models reject custom temperature

    def _raw_send(self, prompt, model, temperature=0.95):
        keyless = self.service_name in self.KEYLESS
        if not self.keys and not keyless:
            return False, f"No API keys found. Please add {self.service_name.capitalize()} API keys with the 🔑 button."

        last_error_msg = "Unknown error occurred."
        keys_to_try = self.keys if self.keys else [""]
        timeout = self.timeout_override or {"lmstudio": 300, "ninerouter": 180}.get(self.service_name, 120)

        for attempt in range(len(keys_to_try)):
            if self.key_index >= len(keys_to_try):
                self.key_index = 0

            current_key = (keys_to_try[self.key_index] or "").strip()
            headers = {"Content-Type": "application/json"}
            if current_key and self.service_name != "lmstudio":
                headers["Authorization"] = f"Bearer {current_key}"

            data = {"model": model.strip(), "messages": [{"role": "user", "content": prompt}]}
            if not self._no_temperature(model):
                data["temperature"] = temperature

            try:
                response = requests.post(self.endpoint, headers=headers, json=data, timeout=timeout)
                if response.status_code == 400 and "temperature" in data and "temperature" in response.text.lower():
                    data.pop("temperature")                        # model refuses custom temperature -> retry
                    response = requests.post(self.endpoint, headers=headers, json=data, timeout=timeout)

                if response.status_code == 200:
                    content = clean_ai_text(response.json()['choices'][0]['message']['content'])
                    if content:
                        return True, content
                    last_error_msg = "The model returned an empty reply. Try again or pick another model."
                    self.key_index = (self.key_index + 1) % len(keys_to_try)
                    continue
                elif response.status_code == 429:
                    last_error_msg = f"Rate limit (429) hit on Key #{self.key_index + 1}. Auto-rotating..."
                    self.key_index = (self.key_index + 1) % len(keys_to_try)
                    time.sleep(0.5)
                    continue
                else:
                    try: api_err = response.json().get("error", {}).get("message", response.text)
                    except Exception: api_err = response.text
                    last_error_msg = f"API Error (Status {response.status_code}):\n{api_err}"
                    low = str(api_err).lower()
                    if response.status_code in (400, 404) and any(w in low for w in ("model", "decommission", "deprecat", "not found", "does not exist")):
                        last_error_msg += "\n\nThis model may be retired or unavailable for your account. Pick another model in Setup > AI Backend Models, or type a name in 'Custom model name'."
                    if response.status_code in [400, 401, 403]:
                        self.key_index = (self.key_index + 1) % len(keys_to_try)
                        if keyless: return False, last_error_msg
                        continue
                    if keyless: return False, last_error_msg
                    break
            except requests.exceptions.ConnectionError as e:
                last_error_msg = f"Network error: {e}"
                log_error(last_error_msg)
                if self.service_name == "lmstudio": return False, "Could not connect to LM Studio. Ensure it is running on port 1234."
                if self.service_name == "ninerouter":
                    return False, (f"Could not connect to 9Router at {self.endpoint}.\n\n"
                                   "1. Install & start it on your PC: npm install -g 9router, then run: 9router\n"
                                   "2. Open http://localhost:20128 and connect a free provider (Kiro AI or OpenCode Free).\n"
                                   "3. On a phone use your PC's Wi-Fi IP (not localhost) and start 9Router with HOSTNAME=0.0.0.0.")
                self.key_index = (self.key_index + 1) % len(keys_to_try)
                continue
            except Exception as e:
                last_error_msg = f"Network error: {e}"
                log_error(last_error_msg)
                if self.service_name == "lmstudio": return False, last_error_msg
                self.key_index = (self.key_index + 1) % len(keys_to_try)
                continue

        return False, f"Failed to process request. All API keys exhausted.\n\nLast error:\n{last_error_msg}"

class GroqBackend(OpenAICompatibleBackend):
    def __init__(self, config_file): super().__init__(config_file, "groq", "https://api.groq.com/openai/v1/chat/completions")
class OpenAIBackend(OpenAICompatibleBackend):
    def __init__(self, config_file): super().__init__(config_file, "openai", "https://api.openai.com/v1/chat/completions")
class LMStudioBackend(OpenAICompatibleBackend):
    def __init__(self, config_file): super().__init__(config_file, "lmstudio", "http://localhost:1234/v1/chat/completions")
class NineRouterBackend(OpenAICompatibleBackend):
    """9Router: free local AI router (OpenAI-compatible). Key optional."""
    def __init__(self, config_file): super().__init__(config_file, "ninerouter", "http://localhost:20128/v1/chat/completions")

class GeminiBackend(BaseBackend):
    def __init__(self, config_file): super().__init__(config_file, "gemini")

    def _raw_send(self, prompt, model, temperature=0.95):
        if not self.keys: return False, "No API keys found. Please add Gemini API keys in the settings."
        last_error_msg = "Unknown error occurred."

        for attempt in range(len(self.keys)):
            if self.key_index >= len(self.keys): self.key_index = 0
            current_key = self.keys[self.key_index]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model.strip()}:generateContent?key={current_key.strip()}"
            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature},
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }

            try:
                response = requests.post(url, headers=headers, json=data, timeout=90)
                if response.status_code == 200:
                    try:
                        candidate = response.json()['candidates'][0]
                        if 'content' in candidate:
                            parts = candidate['content'].get('parts') or []
                            content = clean_ai_text("".join(p.get('text', '') for p in parts if not p.get('thought')))
                            if content:
                                return True, content
                            last_error_msg = "Gemini returned an empty reply."
                            self.key_index = (self.key_index + 1) % len(self.keys)
                            continue
                        else:
                            last_error_msg = f"Gemini blocked the response. Reason: {candidate.get('finishReason', 'Unknown')}"
                            self.key_index = (self.key_index + 1) % len(self.keys)
                            continue
                    except (KeyError, IndexError) as e:
                        last_error_msg = f"Unexpected response format from Gemini: {e}"
                        self.key_index = (self.key_index + 1) % len(self.keys)
                        continue
                elif response.status_code == 429:
                    last_error_msg = f"Rate limit (429) hit on Key #{self.key_index + 1}. Auto-rotating to next key..."
                    self.key_index = (self.key_index + 1) % len(self.keys)
                    time.sleep(0.5)
                    continue
                else:
                    try: api_err = response.json().get("error", {}).get("message", response.text)
                    except json.JSONDecodeError: api_err = response.text
                    last_error_msg = f"API Error (Status {response.status_code}):\n{api_err}"
                    if response.status_code in [400, 403]:
                        self.key_index = (self.key_index + 1) % len(self.keys)
                        continue
                    if response.status_code == 404: last_error_msg += f"\n\nHint: The model '{model}' may not be available for your region. Pick another model (e.g. 'gemini-3.8-flash') in Setup > AI Backend Models."
                    break
            except Exception as e:
                last_error_msg = f"Network error: {e}"
                log_error(last_error_msg)
                self.key_index = (self.key_index + 1) % len(self.keys)
                continue

        return False, f"Failed to generate. All API keys exhausted or rate limited.\n\nLast error:\n{last_error_msg}"


class ClaudeBackend(BaseBackend):
    """Anthropic Messages API (pay-as-you-go; key from console.anthropic.com)."""
    def __init__(self, config_file): super().__init__(config_file, "claude")

    def _raw_send(self, prompt, model, temperature=0.95):
        if not self.keys:
            return False, "No Claude API keys found. Create one at console.anthropic.com and add it with the 🔑 button."
        last_error_msg = "Unknown error occurred."
        for attempt in range(len(self.keys)):
            if self.key_index >= len(self.keys): self.key_index = 0
            headers = {"x-api-key": self.keys[self.key_index].strip(), "anthropic-version": "2023-06-01", "content-type": "application/json"}
            data = {"model": model.strip(), "max_tokens": 8192, "temperature": min(float(temperature), 1.0),
                    "messages": [{"role": "user", "content": prompt}]}
            try:
                r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data, timeout=180)
                if r.status_code == 400 and "temperature" in r.text.lower():
                    data.pop("temperature")
                    r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data, timeout=180)
                if r.status_code == 200:
                    blocks = r.json().get("content", [])
                    text = clean_ai_text("".join(b.get("text", "") for b in blocks if b.get("type") == "text"))
                    if text:
                        return True, text
                    last_error_msg = "Claude returned an empty reply."
                    self.key_index = (self.key_index + 1) % len(self.keys)
                    continue
                elif r.status_code in (429, 529):
                    last_error_msg = f"Claude is busy or rate-limited ({r.status_code}). Auto-rotating..."
                    self.key_index = (self.key_index + 1) % len(self.keys)
                    time.sleep(1.0)
                    continue
                else:
                    try: api_err = r.json().get("error", {}).get("message", r.text)
                    except Exception: api_err = r.text
                    last_error_msg = f"API Error (Status {r.status_code}):\n{api_err}"
                    if r.status_code == 404:
                        last_error_msg += "\n\nThis model name may be retired. Pick another Claude model in Setup."
                    if r.status_code in (400, 401, 403):
                        self.key_index = (self.key_index + 1) % len(self.keys)
                        continue
                    break
            except Exception as e:
                last_error_msg = f"Network error: {e}"
                log_error(last_error_msg)
                self.key_index = (self.key_index + 1) % len(self.keys)
                continue
        return False, f"Failed to generate. All API keys exhausted or rejected.\n\nLast error:\n{last_error_msg}"

# ==========================================
# 3. TTS ENGINES
# ==========================================
TIKTOK_VOICES = {
    "US Female 1": "en_us_001", "US Female 2 (Jessie)": "en_us_002", "US Male 1": "en_us_006",
    "US Male 2": "en_us_007", "US Male 3": "en_us_009", "US Male 4": "en_us_010",
    "UK Male 1": "en_uk_001", "UK Male 2": "en_uk_003", "AU Female 1": "en_au_001", "AU Male 1": "en_au_002",
    "Char - Ghostface": "en_us_ghostface", "Char - Chewbacca": "en_us_chewbacca",
    "Char - C3PO": "en_us_c3po", "Char - Stitch": "en_us_stitch", "Char - Stormtrooper": "en_us_stormtrooper",
    "Char - Rocket": "en_us_rocket", "Special - Narrator": "en_male_narration",
    "Special - Funny / Wacky": "en_male_funny", "Special - Peaceful / Emotional": "en_female_emotional",
    "Singing - Alto": "en_female_ht_f08_wonderful_world", "Singing - Tenor": "en_male_m03_lobby",
    "Singing - Warm Breeze": "en_female_f08_salut_damour", "Singing - Sunshine Soon": "en_male_m03_sunshine_soon",
    "Intl - French Female": "fr_002", "Intl - French Male": "fr_001", "Intl - Spanish Male": "es_002",
    "Intl - Spanish (MX) Male": "es_mx_002", "Intl - Portuguese (BR) Female": "br_001",
    "Intl - Portuguese (BR) Male": "br_005", "Intl - German Female": "de_001", "Intl - German Male": "de_002",
    "Intl - Japanese Female": "jp_001", "Intl - Japanese Male": "jp_006", "Intl - Korean Male 1": "kr_002",
    "Intl - Korean Female 1": "kr_003"
}

# ---------- shared text cleaning / chunking for cloud TTS ----------
def _tts_clean(text):
    """Removes things TikTok/Edge choke on (curly quotes, dashes, emojis, markdown, divider lines)."""
    t = text or ""
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"), ("—", ", "), ("–", ", "), ("…", "...")):
        t = t.replace(a, b)
    t = re.sub(r"[\U00010000-\U0010FFFF]", "", t)          # emojis
    t = re.sub(r"[*_#\[\]{}<>|~^`\\()]", " ", t)
    lines = []
    for ln in t.split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if not ln or set(ln) <= set("-=. "):
            continue
        if ln[-1] not in ".!?;:,":
            ln += "."
        lines.append(ln)
    return " ".join(lines)


def _tts_chunks(text, limit=180):
    """Sentence-aware chunks (never cuts a word in half)."""
    chunks, cur = [], ""
    for s in re.split(r"(?<=[.!?;:])\s+", text):
        s = s.strip()
        while len(s) > limit:
            cut = s.rfind(" ", 0, limit)
            cut = cut if cut > 40 else limit
            part, s = s[:cut].strip(), s[cut:].strip()
            if cur:
                chunks.append(cur); cur = ""
            chunks.append(part)
        if not s:
            continue
        if len(cur) + len(s) + 1 <= limit:
            cur = (cur + " " + s).strip()
        else:
            if cur: chunks.append(cur)
            cur = s
    if cur: chunks.append(cur)
    return [c for c in chunks if c.strip()]


def _clean_session_id(s):
    s = (s or "").strip().strip('"').strip("'")
    m = re.search(r"sessionid=([^;\s]+)", s)               # whole cookie string pasted
    if m: s = m.group(1)
    return s.strip().rstrip(";")


# ---------- TikTok ----------
TIKTOK_ENDPOINTS = [
    "https://api16-normal-v6.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/",
    "https://api22-normal-c-useast2a.tiktokv.com/media/api/text/speech/invoke/",
]
TIKTOK_UA = "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; es_ES; SM-G988N; Build/NRD90M;tt-ok/3.12.13.1)"
TIKTOK_CODES = {
    1: "the session ID is invalid or expired",
    2: "the text chunk was too long",
    4: "this voice no longer exists on TikTok",
    5: "no session ID was sent",
}
_TIKTOK_STATE = {"ep": 0}


def _tiktok_fetch_chunk(chunk, voice_id, headers):
    """One chunk -> (True, mp3_bytes) or (False, reason). Retries + rotates servers."""
    last = "unknown error"
    n = len(TIKTOK_ENDPOINTS)
    for attempt in range(5):
        idx = (_TIKTOK_STATE["ep"] + attempt) % n
        try:
            res = requests.post(
                TIKTOK_ENDPOINTS[idx],
                params={"text_speaker": voice_id, "req_text": chunk, "speaker_map_type": 0, "aid": 1233},
                headers=headers, timeout=20)
        except Exception as e:
            last = f"network error: {e}"
            time.sleep(1.0)
            continue
        if res.status_code != 200:
            last = f"HTTP {res.status_code} from {TIKTOK_ENDPOINTS[idx].split('/')[2]}"
            time.sleep(1.0 + attempt)
            continue
        try:
            data = res.json()
        except ValueError:
            last = "TikTok returned a non-JSON reply"
            continue
        code = data.get("status_code")
        msg = (data.get("message") or "").replace("’", "'")      # curly apostrophe fix
        vstr = (data.get("data") or {}).get("v_str") if isinstance(data.get("data"), dict) else None
        if vstr and code in (0, None):
            _TIKTOK_STATE["ep"] = idx
            try:
                return True, base64.b64decode(vstr)
            except Exception:
                last = "audio data was corrupt"
                continue
        if code in (2, 4):
            return False, TIKTOK_CODES[code]
        last = TIKTOK_CODES.get(code) or msg or f"status_code {code}"
        time.sleep(1.2 * (attempt + 1))
    return False, last


def generate_tiktok_audio(text, voice_id, session_id, output_path):
    try:
        sid = _clean_session_id(session_id)
        if not sid:
            return False, "TikTok session ID is empty. Open the Voice tab and paste your sessionid cookie."
        chunks = _tts_chunks(_tts_clean(text))
        if not chunks:
            return False, "Nothing to read."
        headers = {"User-Agent": TIKTOK_UA, "Cookie": f"sessionid={sid}"}
        final_audio = b""
        for i, chunk in enumerate(chunks):
            ok, res = _tiktok_fetch_chunk(chunk, voice_id, headers)
            if not ok:
                return False, (
                    f"TikTok TTS failed on part {i + 1} of {len(chunks)}: {str(res).rstrip('.')}.\n\n"
                    "What to try:\n"
                    "1. Get a FRESH sessionid: log in at tiktok.com in your browser, press F12 > Application > Cookies > "
                    "tiktok.com > copy the value of 'sessionid' (not sessionid_ss) into the Voice tab.\n"
                    "2. Pick a different voice (US Female 1 and US Male 1 are the most stable).\n"
                    "3. Wait a minute if you generated a lot (rate limit), then press Read Aloud again.\n"
                    "4. TikTok's endpoint is unofficial and sometimes goes down. Switch TTS Engine to "
                    "'Edge TTS (Free)' (no key needed) or ElevenLabs.")
            final_audio += res
            time.sleep(0.4)
        with open(output_path, "wb") as f:
            f.write(final_audio)
        return True, output_path
    except Exception as e:
        log_error(f"TikTok Audio Error: {e}")
        return False, str(e)


# ---------- Edge TTS (free, no key, PC) ----------
EDGE_VOICES = {
    "US Female - Aria": "en-US-AriaNeural", "US Female - Jenny": "en-US-JennyNeural",
    "US Male - Guy": "en-US-GuyNeural", "US Male - Andrew": "en-US-AndrewNeural",
    "UK Female - Sonia": "en-GB-SoniaNeural", "UK Male - Ryan": "en-GB-RyanNeural",
    "AU Female - Natasha": "en-AU-NatashaNeural",
    "Filipino Female - Blessica": "fil-PH-BlessicaNeural", "Filipino Male - Angelo": "fil-PH-AngeloNeural",
}


def generate_edge_audio(text, voice_id, output_path):
    try:
        import edge_tts
    except ImportError:
        return False, ("Edge TTS is not installed. It is PC-only: close the app, delete the .venv_* folder "
                       "next to the script and start it again (internet needed) so it installs automatically.")
    try:
        clean = _tts_clean(text)
        if not clean:
            return False, "Nothing to read."

        async def _run():
            await edge_tts.Communicate(clean, voice_id).save(output_path)

        asyncio.run(_run())
        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            return True, output_path
        return False, "Edge TTS returned empty audio. Check your internet connection."
    except Exception as e:
        log_error(f"Edge TTS Error: {e}")
        return False, f"Edge TTS error: {e}"


def generate_voicebox_audio(text, server_url, voice_preset, selected_engine, output_path, status_callback=None, cancel_callback=None):
    try:
        base_url = (server_url or "").strip().rstrip('/')
        actual_profile_id = (voice_preset or "").strip() if voice_preset else "default"
        actual_engine = selected_engine if selected_engine != "Auto" else None

        try:
            profiles_req = requests.get(f"{base_url}/profiles", timeout=5)
            if profiles_req.status_code == 200:
                p_data = profiles_req.json()

                items = []
                if isinstance(p_data, list):
                    items = p_data
                elif isinstance(p_data, dict) and "items" in p_data:
                    items = p_data["items"]

                for p in items:
                    if str(p.get("name", "")).lower() == str(actual_profile_id).lower() or str(p.get("id", "")) == str(actual_profile_id):
                        actual_profile_id = p.get("id", actual_profile_id)
                        if selected_engine == "Auto" and p.get("engine"):
                            actual_engine = p.get("engine")
                        break
        except Exception: pass

        endpoint = f"{base_url}/generate"

        vb_text = text.replace('*', '').replace('"', '').replace('[', '').replace(']', '').replace('(', '').replace(')', '').strip()

        payload = {"text": vb_text, "profile_id": actual_profile_id}
        if actual_engine: payload["engine"] = actual_engine

        is_waiting = [True]
        start_time = time.time()

        def progress_tracker():
            while is_waiting[0]:
                if cancel_callback and cancel_callback():
                    break
                elapsed = int(time.time() - start_time)
                if status_callback:
                    status_callback(f"⏳ Voicebox is rendering full audio... Please wait ({elapsed}s)")
                time.sleep(1)

        tracker = threading.Thread(target=progress_tracker, daemon=True)
        tracker.start()

        try:
            response = requests.post(endpoint, json=payload, timeout=1800)
            is_waiting[0] = False

            if response.status_code == 200:
                if response.content.startswith(b'RIFF') or response.content.startswith(b'ID3') or response.headers.get('Content-Type', '').startswith('audio/'):
                    with open(output_path, "wb") as f: f.write(response.content)
                    return True, output_path

                try:
                    data = response.json()

                    b64 = data.get("audio_base64") or data.get("audio") or data.get("data") or data.get("base64")
                    if b64 and isinstance(b64, str) and len(b64) > 100 and not b64.startswith("http") and not b64.startswith("/") and not b64.startswith("C:\\") and not b64.startswith("D:\\"):
                        with open(output_path, "wb") as f: f.write(base64.b64decode(b64))
                        return True, output_path

                    audio_url = data.get("output_file_path") or data.get("output_file_url") or data.get("url") or data.get("path") or data.get("file_path") or data.get("audio_file") or data.get("file")
                    if not audio_url and isinstance(b64, str) and (b64.startswith("http") or b64.startswith("/") or ":" in b64):
                        audio_url = b64

                    if audio_url:
                        audio_url = audio_url.strip('"').strip("'")
                        if os.path.exists(audio_url):
                            shutil.copy2(audio_url, output_path)
                            return True, output_path

                        dl_url = audio_url if audio_url.startswith("http") else f"{base_url}/{audio_url.lstrip('/')}"
                        dl_res = requests.get(dl_url, timeout=120)
                        if dl_res.status_code == 200 and len(dl_res.content) > 100:
                            with open(output_path, "wb") as f: f.write(dl_res.content)
                            return True, output_path

                    gen_id = data.get("id") or data.get("generation_id") or data.get("task_id")
                    if gen_id:
                        is_waiting[0] = True
                        start_time = time.time()
                        tracker = threading.Thread(target=progress_tracker, daemon=True)
                        tracker.start()

                        for attempt in range(900):
                            if cancel_callback and cancel_callback():
                                is_waiting[0] = False
                                return False, "Canceled by user."

                            try:
                                audio_res = requests.get(f"{base_url}/audio/{gen_id}", timeout=20)
                                if audio_res.status_code == 200 and len(audio_res.content) > 100:
                                    is_waiting[0] = False
                                    with open(output_path, "wb") as f: f.write(audio_res.content)
                                    return True, output_path
                            except requests.exceptions.RequestException: pass
                            time.sleep(2)
                        is_waiting[0] = False
                        return False, "Voicebox Audio Error: Polling timed out after 30 minutes."

                    return False, f"Voicebox Error: Unrecognized API JSON structure: {str(data)[:200]}"
                except Exception as e:
                    return False, f"Voicebox JSON Parse Error: {e}"
            else:
                is_waiting[0] = False
                return False, f"Voicebox API Error: {response.status_code} - {response.text[:100]}"

        except requests.exceptions.Timeout:
            is_waiting[0] = False
            return False, "Voicebox Server Error: Generation timed out after 30 minutes."
        except Exception as req_e:
            is_waiting[0] = False
            return False, f"Voicebox Request Error: {req_e}"

    except Exception as e:
        log_error(f"Voicebox Engine Error: {e}")
        return False, f"Voicebox Engine Error: {e}"

def generate_elevenlabs_audio(text, presets, start_preset_name, output_path):
    if not presets: return False, "No ElevenLabs presets found. Please click '⚙️ Manage ElevenLabs Keys' to add your accounts.", start_preset_name

    preset_keys = list(presets.keys())
    start_index = preset_keys.index(start_preset_name) if start_preset_name in preset_keys else 0
    payload = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}

    error_messages = []

    for attempt in range(len(preset_keys)):
        current_idx = (start_index + attempt) % len(preset_keys)
        active_preset_name = preset_keys[current_idx]
        preset_data = presets[active_preset_name]

        if isinstance(preset_data, str):
            active_voice_id, current_key = preset_data, ""
        else:
            active_voice_id = preset_data.get("voice_id", "")
            current_key = preset_data.get("api_key", "")

        if not current_key or not active_voice_id:
            error_messages.append(f"[{active_preset_name}] Failed: Missing API Key or Voice ID.")
            continue

        active_voice_id = active_voice_id.strip()
        current_key = current_key.strip()

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{active_voice_id}?output_format=mp3_44100_128"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": current_key}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=300)
            if response.status_code == 200:
                with open(output_path, "wb") as f: f.write(response.content)
                return True, output_path, active_preset_name
            else:
                try: err_json = response.json()
                except: err_json = response.text

                err_str = f"[{active_preset_name}] Rejected (Status {response.status_code}): {err_json}"
                error_messages.append(err_str)
                log_error(f"ElevenLabs Rotation: {err_str}")
                continue
        except requests.exceptions.ConnectionError:
            error_messages.append(f"[{active_preset_name}] Failed: Connection Refused.")
            break
        except Exception as e:
            err_str = f"[{active_preset_name}] Network Error: {e}"
            error_messages.append(err_str)
            log_error(f"ElevenLabs Rotation: {err_str}")
            continue

    # If we get here, absolutely every key failed.
    summary_text = "\n\n".join(error_messages)
    return False, f"ElevenLabs Failed. All presets were tested and rejected by their servers.\n\n--- Breakdown ---\n{summary_text}", start_preset_name

def generate_fish_speech_audio(text, server_url, presets, start_preset_name, output_path, status_callback=None, cancel_callback=None):
    if not presets or not server_url: return False, "Missing Fish Speech Setup.", start_preset_name

    base_url = (server_url or "").strip().rstrip('/')

    if "0.0.0.0" in base_url:
        base_url = base_url.replace("0.0.0.0", "127.0.0.1")

    preset_data = presets.get(start_preset_name, {})
    ref_audio_path = preset_data.get("audio", "")
    ref_text_path = preset_data.get("text", "")

    ref_audio_path = ref_audio_path.strip('\"\'')
    ref_text_path = ref_text_path.strip('\"\'')

    if not ref_audio_path or not os.path.exists(ref_audio_path):
        return False, f"Reference audio not found for preset '{start_preset_name}'. Please verify the path.", start_preset_name

    ref_text_content = ""
    if ref_text_path and os.path.exists(ref_text_path):
        try:
            with open(ref_text_path, "r", encoding="utf-8") as f:
                ref_text_content = f.read().strip()
        except Exception as e:
            pass

    endpoint = f"{base_url}/v1/tts"

    is_waiting = [True]
    start_time = time.time()

    def progress_tracker():
        while is_waiting[0]:
            if cancel_callback and cancel_callback():
                break
            elapsed = int(time.time() - start_time)
            if status_callback:
                status_callback(f"⏳ Fish Speech is rendering... Please wait ({elapsed}s)")
            time.sleep(1)

    tracker = threading.Thread(target=progress_tracker, daemon=True)
    tracker.start()

    try:
        with open(ref_audio_path, 'rb') as f_audio:
            audio_b64 = base64.b64encode(f_audio.read()).decode('utf-8')

        payload = {
             "text": text,
             "format": "wav",
             "references": [
                 {
                     "audio": audio_b64,
                     "text": ref_text_content
                 }
             ],
             "normalize": True
        }

        print(f"[Fish Speech] 🌐 Connecting to RAW API Server at {endpoint}...")

        headers = {"Content-Type": "application/json"}
        response = requests.post(endpoint, json=payload, headers=headers, timeout=1800)
        is_waiting[0] = False

        if response.status_code == 200:
             if response.headers.get('Content-Type', '').startswith('audio/'):
                 with open(output_path, "wb") as out_f:
                     out_f.write(response.content)
                 return True, output_path, start_preset_name
             else:
                 try:
                     data = response.json()
                     b64 = data.get("audio_base64") or data.get("audio") or data.get("data")
                     if b64:
                         with open(output_path, "wb") as out_f:
                             out_f.write(base64.b64decode(b64))
                         return True, output_path, start_preset_name
                 except: pass
                 return False, "Fish Speech Error: Unknown API response format.", start_preset_name
        else:
             return False, f"Fish Speech Error: {response.status_code} - {response.text[:200]}", start_preset_name

    except requests.exceptions.ConnectionError:
         is_waiting[0] = False
         return False, f"Connection Refused to {base_url}. Ensure your Fish Speech Server is running.", start_preset_name
    except requests.exceptions.Timeout:
         is_waiting[0] = False
         return False, "Connection Timed Out. The GPU server took more than 30 minutes to respond!", start_preset_name
    except Exception as e:
         is_waiting[0] = False
         log_error(f"Fish Speech RAW API Error: {e}")
         return False, f"Fish Speech RAW API Error: {e}", start_preset_name


# ==========================================
# 4. TEXT HELPERS
# ==========================================
def format_and_clean(text):
    text = text.replace("**", "")
    text = re.sub(r'(?i)(date|petsa)\s*:', 'Date:', text)
    text = re.sub(r'(?i)(bible verse|verso|bersikulo|talata)\s*:', 'Verse:', text)
    text = re.sub(r'(?i)(pagninilay|repleksyon)\s*:', 'Reflection:', text)
    text = re.sub(r'(?i)(panalangin|dasal)\s*:', 'Prayer:', text)
    headers = ['Date:', 'Verse:', 'Reflection:', 'Prayer:', 'Title:', 'Main Text:', 'Introduction:', 'Key Points:', 'Conclusion:', 'Passage:', 'Context & Background:', 'Observation Questions:', 'Application Questions:', 'Story Title:', 'Inspired By Verse:', 'Story:', 'Poem Title:', 'Scripture Inspiration:', 'Poem:', 'Focus Verse:', 'Adoration:', 'Confession:', 'Thanksgiving:', 'Supplication:', 'Answer:', 'S - Scripture:', 'O - Observation:', 'A - Application:', 'P - Prayer:', 'The Verse:', 'The Understanding:', 'The Reflection:', 'The Prayer:', 'Focus Promise:', 'Declaration:', 'The Brain-Dump:', 'The Anchor Verse:', 'The Exchange:', 'Breath Verse:', 'Actionable Focus:', 'Realtalk Verse:', 'The Realtalk:', 'The Challenge:', 'Short Prayer:']
    for h in headers:
        text = re.sub(r'([^\n])\s*(' + h + r')', r'\1\n\n\2', text)
        text = re.sub(r'(' + h + r')\s*([^\n])', r'\1\n\2', text)
    text = re.sub(r'([^\n])\s*(Question \d+:)', r'\1\n\n\2', text)
    text = re.sub(r'(Question \d+:)\s*([^\n])', r'\1\n\2', text)
    return text.strip()

def extract_title(content):
    lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('---')]
    for i, line in enumerate(lines):
        if line.startswith("Date:"): return lines[i+1][:37] + "..." if i + 1 < len(lines) and len(lines[i+1]) > 40 else lines[i+1] if i + 1 < len(lines) else ""
        elif line.startswith("Title:") or line.startswith("Story Title:") or line.startswith("Poem Title:"):
            v = line.split(":", 1)[-1].strip()
            return v[:37] + "..." if len(v) > 40 else v
        elif line.startswith("Verse:") or line.startswith("Main Text:") or line.startswith("Passage:") or line.startswith("Focus Verse:") or line.startswith("S - Scripture:") or line.startswith("The Verse:") or line.startswith("Focus Promise:") or line.startswith("The Anchor Verse:") or line.startswith("Breath Verse:") or line.startswith("Realtalk Verse:"):
            if i + 1 < len(lines):
                v = lines[i+1]
                return v[:37] + "..." if len(v) > 40 else v
    if lines: return lines[0][:37] + "..." if len(lines[0]) > 40 else lines[0]
    return "Saved Document"

def set_window_size(page, w, h):
    if is_android_sys(): return
    try:
        if page.platform == ft.PagePlatform.ANDROID or page.platform == ft.PagePlatform.IOS:
            return
    except: pass
    try:
        page.window.width = w
        page.window.height = h
    except:
        try:
            page.window_width = w
            page.window_height = h
        except: pass

def build_reading_units(content, size, family):
    """
    Splits the text into small chunks (usually 1 word each), one Text control per chunk,
    laid out as wrapping rows (one row per paragraph). Each chunk has a unique key, so we can
    scroll to the REAL on-screen position of the word being spoken.
    """
    total_words = len(content.split())
    n = 1 if total_words <= 450 else 2 if total_words <= 900 else 4 if total_words <= 1800 else 8
    spacing = max(3, round(size * 0.28))

    meta, ctrls, paragraphs = [], [], []
    word_counter = 0
    for raw_line in content.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        words = line.split()
        row_ctrls = []
        for s in range(0, len(words), n):
            group = words[s:s + n]
            text = " ".join(group)
            weight = float(sum(len(x) + 1 for x in group))
            pause_total, last_pause = 0.0, 0.0
            for gi, x in enumerate(group):
                tail = x.rstrip("\"'”’)]")
                p = 0.0
                if tail.endswith((".", "!", "?", "…")): p = 7.0
                elif tail.endswith((",", ";")): p = 3.0
                elif tail.endswith(":"): p = 5.0
                elif tail.endswith(("—", "–")): p = 3.0
                pause_total += p
                if gi == len(group) - 1: last_pause = p
            is_line_end = (s + n >= len(words))
            if is_line_end:
                pause_total += 5.0
                last_pause += 5.0
            last_word = group[-1].rstrip("\"'”’)]")
            sent_end = is_line_end or last_word.endswith((".", "!", "?", "…"))
            meta.append({"w": weight + pause_total, "last_pause": last_pause, "sent_end": sent_end, "wi": word_counter + s})
            c = ft.Text(text, size=size, color="white", key=f"u{len(ctrls)}", font_family=family)
            ctrls.append(c)
            row_ctrls.append(c)
        paragraphs.append(ft.Row(row_ctrls, wrap=True, spacing=spacing, run_spacing=4))
        word_counter += len(words)
    return meta, ctrls, paragraphs, n

# ==========================================
# 5. FLET MOBILE / DESKTOP GUI
# ==========================================
# Verified against the providers' docs on 2026-10-16 (retired: Groq llama-3.x / mixtral / gemma2,
# Gemini 1.5 / 2.0 / 2.5, OpenAI gpt-3.5 / gpt-4o family).
BACKEND_MODELS = {
    "Groq": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"],
    "Gemini": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-4-argon"],
    "OpenAI": ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.5"],
    "Claude (Anthropic)": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"],
    "9Router (Free)": ["kr/claude-sonnet-4.5"],
    "LM Studio (Local)": ["local-model"],
}

HILITE_COLOR = "#FACC15"      # color of the word being spoken right now
SYNC_LOOKAHEAD = 0.12         # seconds: compensates for the UI render delay (Flet -> screen)

def main(page: ft.Page):
    page.title = "Daily Devotional"

    if is_android_sys():
        page.padding = make_padding(left=5, right=5, top=40, bottom=10)
    else:
        try:
            if page.platform == ft.PagePlatform.ANDROID or page.platform == ft.PagePlatform.IOS:
                page.padding = make_padding(left=5, right=5, top=40, bottom=10)
        except: pass

    app_state = {
        "last_audio_path": "",
        "last_audio_hash": "",
        "is_rendering_audio": False,
        "cancel_render": False,
        "current_render_id": 0
    }
    reading_state = {"ctrls": []}

    set_window_size(page, 450, 850)

    page.scroll = None
    is_audio_playing = [False]
    is_video_recording = [False]
    is_fullscreen = [False]
    current_fullscreen_mode = ["none"]
    selected_fav_idx = [None]

    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#121212"

    top_play_btn = ft.TextButton("▶️", tooltip="Play / Stop Audio")
    top_rec_btn = ft.TextButton("⏺️ Rec", tooltip="Record Screen to MP4", style=ft.ButtonStyle(color="red400"))
    top_reset_voice_btn = ft.TextButton("🔄 RETRY", tooltip="Clear Cache & Retry Voice", style=ft.ButtonStyle(color="orange400"))
    copy_btn = ft.TextButton("📋", tooltip="Copy Text")

    def on_reset_voice_clicked(e):
        try:
            # 1. Forcefully kill the audio engine & release the Windows file lock!
            if PYGAME_AVAILABLE and not is_android_sys() and pygame.mixer.get_init():
                pygame.mixer.music.stop()
                try: pygame.mixer.music.unload() # THIS unlocks the file!
                except: pass
            elif audio_player:
                audio_player.pause()
                audio_player.src = None

            is_audio_playing[0] = False

            # 2. Reset the Play buttons visually
            tts_btn.text = "🔊 Read Aloud"
            tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color="white", shape=ft.RoundedRectangleBorder(radius=8))
            top_play_btn.text = "▶️"
            try:
                tts_btn.update()
                top_play_btn.update()
            except: pass

            # 3. Find and destroy the cache files
            content = text_area.value.strip()
            if not content or content.startswith("Welcome!"):
                show_snack("Nothing to reset.", "orange")
                return

            pure_text_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            cache_dir = getattr(tf_cache_dir, 'value', "").strip()
            if not cache_dir: cache_dir = DATA_DIR

            wiped = False

            # Destroy the permanent cached audio
            for ext in AUDIO_EXTS:
                pure_path = os.path.join(cache_dir, f"{pure_text_hash}{ext}")
                if os.path.exists(pure_path):
                    try:
                        os.remove(pure_path)
                        wiped = True
                    except Exception as err:
                        print(f"File locked: {err}")

            # Destroy the temporary streaming files
            for f in os.listdir(DATA_DIR):
                if f.startswith("tts_output_") or f.startswith("play_"):
                    try:
                        os.remove(os.path.join(DATA_DIR, f))
                        wiped = True
                    except: pass

            app_state["last_audio_path"] = ""
            app_state["last_audio_hash"] = ""

            if wiped:
                show_snack("🔄 Cache wiped! Pick a new voice and click Read Aloud.", "blue")
            else:
                show_snack("✅ Engine reset. Ready to generate.", "green")

            page.update()
        except Exception as ex:
            show_snack(f"Reset Error: {ex}", "red")
            page.update()

    top_reset_voice_btn.on_click = on_reset_voice_clicked

    generate_btn = ft.TextButton("✨ 1 Click Generate Content", expand=True, style=ft.ButtonStyle(bgcolor="#2563EB", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    prompt_gen_btn = ft.TextButton("🧠 Prompt Generate", expand=True, style=ft.ButtonStyle(bgcolor="#374151", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    revise_btn = ft.TextButton("🔄 Revise", expand=True, style=ft.ButtonStyle(bgcolor="#D97706", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    prompt_rev_btn = ft.TextButton("✍️ Prompt Revise", expand=True, style=ft.ButtonStyle(bgcolor="#D97706", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    translate_btn = ft.TextButton("📖 Translate Verse", expand=True, style=ft.ButtonStyle(bgcolor="#059669", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    qa_btn = ft.TextButton("❓ Generate Q&A", expand=True, style=ft.ButtonStyle(bgcolor="#6D28D9", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    tts_btn = ft.TextButton("🔊 Read Aloud", expand=True, style=ft.ButtonStyle(bgcolor="#0284C7", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    save_btn = ft.TextButton("❤️ Save", expand=True, style=ft.ButtonStyle(bgcolor="#B91C1C", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    backup_btn = ft.TextButton("💾 Backup Data", expand=True, style=ft.ButtonStyle(bgcolor="#0F766E", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    restore_btn = ft.TextButton("📂 Restore Data", expand=True, style=ft.ButtonStyle(bgcolor="#0F766E", color="white", shape=ft.RoundedRectangleBorder(radius=8)))
    link_audio_btn = ft.TextButton("🔗 Link Existing Audio", expand=True, style=ft.ButtonStyle(bgcolor="#4F46E5", color="white", shape=ft.RoundedRectangleBorder(radius=8)))

    el_manage_btn = ft.TextButton("⚙️ Manage ElevenLabs Keys", style=ft.ButtonStyle(bgcolor="grey800", color="white"))
    fish_manage_btn = ft.TextButton("🐟 Manage Fish Speech", style=ft.ButtonStyle(bgcolor="grey800", color="white"))
    test_vb_btn = ft.TextButton("🔌 Test PC Voicebox Link", style=ft.ButtonStyle(bgcolor="green700", color="white"))
    btn_browse_cache = ft.TextButton("📂 Browse")
    btn_clear_cache = ft.TextButton("🗑️ Clear Cache", style=ft.ButtonStyle(color="red400"))

    chk_autoplay = ft.Checkbox(label="Auto-Play Audio", value=True)
    chk_force_cache = ft.Checkbox(label="Force Cache Only (Silent if missing)", value=False)
    chk_safe_audio = ft.Checkbox(label="Bypass Red Screen (Browser Audio Fallback)", value=False)
    chk_highlight = ft.Checkbox(label="Highlight spoken word", value=True)
    chk_autoscroll = ft.Checkbox(label="Auto-scroll with voice", value=True)
    chk_autoheal = ft.Checkbox(label="Auto-heal AI models (switch automatically if one is retired or exhausted)", value=True)
    dd_sync_engine = ft.Dropdown(label="Sync Engine", options=[ft.dropdown.Option(x) for x in ["Auto", "Local Whisper (PC)", "Cloud Whisper (Groq)", "Classic (Silence)"]])
    dd_whisper_model = ft.Dropdown(label="Local Whisper Model", options=[ft.dropdown.Option(x) for x in ["tiny", "base", "small"]])

    # Sync fine-tune: 20 = 0.0s. Each step = 0.1s. Range -2.0s .. +2.0s
    scroll_speed_slider = ft.Slider(min=0, max=40, divisions=40, value=20)
    slider_label = ft.Text("+0.0s", size=14, weight="bold", color="blue400")

    fav_list = ft.ListView(spacing=5, expand=True)

    default_welcome_txt = "Welcome!\n\nTap '✨ 1 Click Generate Content' below to receive your daily Verse, Reflection, and Prayer.\n\nYou can also type your own document here manually and tap 'Save ❤️' to keep it."

    loaded_text = ""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_text = json.load(f).get("last_devotion_text", "")
        except Exception: pass

    if not loaded_text or not loaded_text.strip():
        loaded_text = default_welcome_txt

    text_area = ft.TextField(
        multiline=True, border_radius=10, border_color="blue600", border_width=1.5,
        width=float('inf'), expand=True,
        value=loaded_text
    )

    fav_text_area = ft.TextField(
        multiline=True, read_only=True, border_radius=10, border_color="blue600", border_width=1.5,
        width=float('inf'), expand=True,
        value="Select a favorite document to read here..."
    )

    # Hidden legacy holder (kept so font settings code keeps working)
    reading_text = ft.Text(value="", size=16, selectable=True, color="white", visible=False)
    # The real reading view: one Text per word/chunk (built when playback starts)
    reading_body = ft.Column([], spacing=10)
    reading_column = ft.Column([reading_text, reading_body], scroll="hidden", expand=True)
    reading_container = ft.Container(
        content=reading_column, border_radius=10, border=make_border(1.5, "blue600"),
        padding=make_padding(left=20, right=20, top=15, bottom=15), expand=True
    )

    tf_tiktok_session = ft.TextField(label="TikTok Session ID", password=True)
    dd_tiktok_voice = ft.Dropdown(label="TikTok Voice Preset", options=[ft.dropdown.Option(x) for x in TIKTOK_VOICES.keys()])
    tf_voicebox_url = ft.TextField(label="Voicebox PC URL (e.g. http://192.168.1.X:17493)")
    tf_voicebox_preset = ft.TextField(label="Voicebox Preset (Optional)")
    dd_voicebox_engine = ft.Dropdown(label="Voicebox Engine", options=[ft.dropdown.Option(x) for x in ["Auto", "kokoro", "q", "xtts", "piper", "styletts2"]])
    tf_fish_url = ft.TextField(label="Fish Speech Server (Gradio URL or HF Space)")
    tf_cache_dir = ft.TextField(label="Offline Audio Cache Folder (For Backup/Favorites)", expand=True)

    dd_format = ft.Dropdown(label="Format / Presentation", options=[ft.dropdown.Option(x) for x in ["Standard Devotional", "Realtalk Devotional", "Sermon Outline", "Bible Study Guide", "Short Story / Parable", "Poem", "Prayer Focus", "S.O.A.P. Method", "Understanding Format", "Declarative Style", "Journaling / Brain-Dump", "One-Verse Breath Focus", "Three-Part Devotional"]])
    dd_style = ft.Dropdown(label="Style", options=[ft.dropdown.Option(x) for x in ["Uplifting & Encouraging", "Deep & Theological", "Modern & Practical", "Short & Direct", "Poetic & Contemplative", "Direct person Target"]])
    dd_version = ft.Dropdown(label="Bible Version", options=[ft.dropdown.Option(x) for x in ["NIV (New International Version)", "ESV (English Standard Version)", "KJV (King James Version)", "NLT (New Living Translation)", "Tagalog: Magandang Balita Biblia (MBBTAG)", "Tagalog: Ang Dating Biblia (1905)", "Tagalog: Ang Salita ng Diyos (SND)"]])
    dd_theme = ft.Dropdown(label="Theme", options=[ft.dropdown.Option(x) for x in ["Random", "Hope", "Faith", "God's Love", "Courage", "Patience", "Forgiveness", "Joy", "Peace", "Grace", "Mercy", "Strength", "Healing", "Trusting God", "Wisdom", "Compassion", "Humility", "Perseverance", "Gratitude", "Kindness", "Obedience", "Overcoming Fear", "Guidance", "Comfort in Sorrow", "God's Promises", "Light in Darkness", "Fellowship", "Worship", "Praising God", "The Holy Spirit", "Creation", "Redemption", "Serving Others"]])
    dd_length = ft.Dropdown(label="Length", options=[ft.dropdown.Option(x) for x in ["Short (1 paragraph)", "Medium (2 paragraphs)", "Long (3-4 paragraphs)", "In-Depth (5+ paragraphs)"]])
    dd_lang = ft.Dropdown(label="Language", options=[ft.dropdown.Option(x) for x in ["English", "Native Tagalog", "Taglish", "Modern Tagalog", "Conyo"]])
    dd_duration = ft.Dropdown(label="Duration", options=[ft.dropdown.Option(x) for x in ["1 Day", "2 Days", "3 Days", "5 Days", "7 Days (1 Week)"]])
    dd_font = ft.Dropdown(label="Font", options=[ft.dropdown.Option(x) for x in ["Default", "Georgia", "Helvetica", "Arial", "Times New Roman", "Courier", "Verdana", "Trebuchet MS"]])
    dd_size = ft.Dropdown(label="Font Size", options=[ft.dropdown.Option(x) for x in ["12", "14", "15", "16", "18", "20", "22", "24"]])
    dd_tts_engine = ft.Dropdown(label="TTS Engine", options=[ft.dropdown.Option(x) for x in ["TikTok API", "Local PC Voicebox", "ElevenLabs", "Fish Speech"] + ([] if is_android_sys() else ["Edge TTS (Free)"])])
    dd_elevenlabs_preset = ft.Dropdown(label="ElevenLabs Preset", options=[])
    dd_fish_preset = ft.Dropdown(label="Fish Speech Preset", options=[])
    dd_edge_voice = ft.Dropdown(label="Edge TTS Voice", options=[ft.dropdown.Option(x) for x in EDGE_VOICES.keys()])

    dd_model = ft.Dropdown(label="AI Model", options=[ft.dropdown.Option(x) for x in BACKEND_MODELS["Groq"]])
    dd_backend = ft.Dropdown(label="Powered by AI", options=[ft.dropdown.Option(x) for x in BACKEND_MODELS.keys()])
    tf_custom_model = ft.TextField(label="Custom model name (optional - overrides the list)")
    tf_9router_url = ft.TextField(label="9Router URL (PC: http://localhost:20128/v1)", visible=False)
    btn_heal_models = ft.TextButton("🩺 Test & Fix Models", style=ft.ButtonStyle(bgcolor="green700", color="white"))

    def on_audio_state_changed(e):
        if hasattr(e, 'data') and e.data == "completed":
            is_audio_playing[0] = False
            tts_btn.text = "🔊 Read Aloud"
            tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color="white", shape=ft.RoundedRectangleBorder(radius=8))
            top_play_btn.text = "▶️"

            if current_fullscreen_mode[0] == "none" or current_fullscreen_mode[0] == "window":
                reading_container.border = make_border(1.5, "blue600")
            text_container_gen.content = text_area
            if is_video_recording[0]: is_video_recording[0] = False
            try:
                text_container_gen.update()
                page.update()
            except: pass

    # =========================================================
    # Android uses the Flet Audio control. PC uses PyGame instead.
    # =========================================================
    # Android: the player reports its REAL position -> perfect highlight sync
    android_clock = {"pos": 0.0, "t": 0.0, "got": False, "dur": 0.0}

    def on_audio_position(e):
        try:
            android_clock["pos"] = float(e.data) / 1000.0
            android_clock["t"] = time.time()
            android_clock["got"] = True
        except Exception: pass

    def on_audio_duration(e):
        try: android_clock["dur"] = float(e.data) / 1000.0
        except Exception: pass

    audio_player = None
    if is_android_sys() and Audio is not None:
        try:
            try:
                audio_player = Audio(src_base64=_silent_wav_b64(), autoplay=False)
            except TypeError:
                audio_player = Audio(autoplay=False)
            audio_player.on_state_changed = on_audio_state_changed
            try:
                audio_player.on_position_changed = on_audio_position
                audio_player.on_duration_changed = on_audio_duration
            except Exception: pass
            page.overlay.append(audio_player)
        except Exception as ex:
            log_error(f"Audio control init failed: {ex}")

    groq_backend = GroqBackend(CONFIG_FILE)
    gemini_backend = GeminiBackend(CONFIG_FILE)
    openai_backend = OpenAIBackend(CONFIG_FILE)
    lmstudio_backend = LMStudioBackend(CONFIG_FILE)
    claude_backend = ClaudeBackend(CONFIG_FILE)
    nine_backend = NineRouterBackend(CONFIG_FILE)

    favorites = []
    app_settings = {}

    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, 'r') as f: favorites = json.load(f)
        except json.JSONDecodeError: pass

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: app_settings = json.load(f)
        except json.JSONDecodeError: pass

    # --- LOAD SETTINGS TO ELEMENTS ---
    dd_format.value = app_settings.get("format", "Standard Devotional")
    dd_style.value = app_settings.get("style", "Uplifting & Encouraging")
    dd_version.value = app_settings.get("version", "NIV (New International Version)")
    dd_theme.value = app_settings.get("theme", "Random")
    dd_length.value = app_settings.get("length", "Medium (2 paragraphs)")
    dd_lang.value = app_settings.get("lang", "English")
    dd_duration.value = app_settings.get("duration", "1 Day")
    dd_font.value = app_settings.get("font", "Default")
    dd_size.value = app_settings.get("size", "16")
    dd_tts_engine.value = app_settings.get("tts_engine", "TikTok API")
    dd_backend.value = app_settings.get("backend", "Groq")
    if dd_backend.value not in BACKEND_MODELS: dd_backend.value = "Groq"
    dd_model.value = app_settings.get("model", "")          # validated in apply_backend_models()
    tf_custom_model.value = app_settings.get("custom_model", "")
    tf_9router_url.value = app_settings.get("ninerouter_url", "http://localhost:20128/v1")

    chk_autoplay.value = app_settings.get("autoplay", True)
    chk_force_cache.value = app_settings.get("force_cache", False)
    chk_safe_audio.value = app_settings.get("safe_audio", False)
    chk_highlight.value = app_settings.get("highlight", True)
    chk_autoscroll.value = app_settings.get("autoscroll", True)
    chk_autoheal.value = app_settings.get("auto_heal", True)
    dd_sync_engine.value = app_settings.get("sync_engine", "Auto")
    if dd_sync_engine.value not in ["Auto", "Local Whisper (PC)", "Cloud Whisper (Groq)", "Classic (Silence)"]:
        dd_sync_engine.value = "Auto"
    dd_whisper_model.value = app_settings.get("whisper_model", "base")
    dd_edge_voice.value = app_settings.get("edge_voice", "US Female - Aria")
    if dd_edge_voice.value not in EDGE_VOICES: dd_edge_voice.value = "US Female - Aria"

    try: saved_scroll_speed = max(0, min(40, float(app_settings.get("scroll_speed", 20))))
    except Exception: saved_scroll_speed = 20
    scroll_speed_slider.value = saved_scroll_speed
    slider_label.value = f"{(saved_scroll_speed - 20) * 0.1:+.1f}s"

    tf_tiktok_session.value = app_settings.get("tiktok_session_id", "")
    dd_tiktok_voice.value = app_settings.get("tiktok_voice", "US Female 2 (Jessie)")
    tf_voicebox_url.value = app_settings.get("voicebox_url", "")
    tf_voicebox_preset.value = app_settings.get("voicebox_preset", "")
    dd_voicebox_engine.value = app_settings.get("voicebox_engine", "Auto")
    tf_fish_url.value = app_settings.get("fish_url", "http://127.0.0.1:8080")
    tf_cache_dir.value = app_settings.get("audio_cache_dir", os.path.join(DATA_DIR, "audio_cache"))

    el_presets_dict = app_settings.get("elevenlabs_presets", {})
    dd_elevenlabs_preset.options = [ft.dropdown.Option(x) for x in el_presets_dict.keys()]
    el_active_val = app_settings.get("elevenlabs_active_preset", "")
    if el_active_val not in el_presets_dict and el_presets_dict: el_active_val = list(el_presets_dict.keys())[0]
    dd_elevenlabs_preset.value = el_active_val

    fish_presets_dict = app_settings.get("fish_presets", {})
    dd_fish_preset.options = [ft.dropdown.Option(x) for x in fish_presets_dict.keys()]
    fish_active_val = app_settings.get("fish_active_preset", "")
    if fish_active_val not in fish_presets_dict and fish_presets_dict: fish_active_val = list(fish_presets_dict.keys())[0]
    dd_fish_preset.value = fish_active_val

    def save_favorites():
        try:
            with open(FAVORITES_FILE, 'w') as f: json.dump(favorites, f, indent=4)
        except Exception as e: print(f"Error saving favorites: {e}")

    # ==========================================
    # UNIVERSAL POPUP LOGIC
    # ==========================================
    def show_snack(msg, color="green"):
        snack = ft.SnackBar(content=ft.Text(msg), bgcolor=color, open=True)
        try:
            if hasattr(page, 'open'): page.open(snack)
            else:
                page.snack_bar = snack
                page.update()
        except Exception as e: print(f"Snackbar Alert: {msg}")

    def show_dialog(dlg):
        try:
            if hasattr(page, 'open'): page.open(dlg)
            else:
                if dlg not in page.overlay: page.overlay.append(dlg)
                page.dialog = dlg
                dlg.open = True
                page.update()
        except Exception as e: print(f"Dialog Error: {e}")

    def hide_dialog(dlg):
        try:
            if hasattr(page, 'close'): page.close(dlg)
            else:
                dlg.open = False
                page.update()
        except Exception as e: pass

    def ui_call(fn):
        if hasattr(page, 'call_after'): page.call_after(fn)
        else: fn()

    def show_error_dialog(error_msg):
        dlg = ft.AlertDialog(
            title=ft.Text("Alert", color="red400"),
            content=ft.Column([
                ft.Text("The provider returned the following message:", size=12),
                ft.TextField(value=error_msg, multiline=True, read_only=True, min_lines=6, max_lines=12, text_size=11)
            ], tight=True),
        )
        dlg.actions = [ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        show_dialog(dlg)

    def perform_backup(e):
        try:
            chk_settings = ft.Checkbox(label="Include Settings & API Keys", value=True)
            chk_favorites = ft.Checkbox(label="Include Favorites", value=True)
            backup_field = ft.TextField(value="", multiline=True, read_only=True, min_lines=4, max_lines=8, label="Raw Backup Code:")
            file_status_text = ft.Text("", size=11, color="green400")

            def generate_backup_str(e=None):
                data_to_save = {}
                if chk_favorites.value:
                    data_to_save["favorites"] = favorites

                if chk_settings.value:
                    data_to_save.update({
                        "format": dd_format.value,
                        "style": dd_style.value,
                        "version": dd_version.value,
                        "theme": dd_theme.value,
                        "length": dd_length.value,
                        "lang": dd_lang.value,
                        "duration": dd_duration.value,
                        "font": dd_font.value,
                        "size": dd_size.value,
                        "model": dd_model.value,
                        "backend": dd_backend.value,
                        "groq_keys": groq_backend.keys,
                        "gemini_keys": gemini_backend.keys,
                        "openai_keys": openai_backend.keys,
                        "claude_keys": claude_backend.keys,
                        "ninerouter_keys": nine_backend.keys,
                        "ninerouter_url": (tf_9router_url.value or "").strip(),
                        "custom_model": (tf_custom_model.value or "").strip(),
                        "tiktok_session_id": (tf_tiktok_session.value or "").strip(),
                        "tiktok_voice": dd_tiktok_voice.value,
                        "voicebox_url": (tf_voicebox_url.value or "").strip(),
                        "voicebox_preset": (tf_voicebox_preset.value or "").strip(),
                        "voicebox_engine": getattr(dd_voicebox_engine, 'value', "Auto"),
                        "fish_url": (tf_fish_url.value or "").strip(),
                        "tts_engine": dd_tts_engine.value,
                        "autoplay": chk_autoplay.value,
                        "force_cache": chk_force_cache.value,
                        "safe_audio": chk_safe_audio.value,
                        "highlight": chk_highlight.value,
                        "auto_heal": chk_autoheal.value,
                        "autoscroll": chk_autoscroll.value,
                        "sync_engine": dd_sync_engine.value,
                        "whisper_model": dd_whisper_model.value,
                        "edge_voice": dd_edge_voice.value,
                        "scroll_speed": scroll_speed_slider.value,
                        "elevenlabs_presets": app_settings.get("elevenlabs_presets", {}),
                        "elevenlabs_active_preset": getattr(dd_elevenlabs_preset, 'value', ""),
                        "fish_presets": app_settings.get("fish_presets", {}),
                        "fish_active_preset": getattr(dd_fish_preset, 'value', ""),
                        "audio_cache_dir": getattr(tf_cache_dir, 'value', "")
                    })

                if not data_to_save:
                    backup_field.value = ""
                    file_status_text.value = "⚠️ Nothing selected to backup."
                    try:
                        backup_field.update()
                        file_status_text.update()
                    except: pass
                    return

                backup_str = json.dumps(data_to_save)
                backup_field.value = backup_str

                cache_dir = getattr(tf_cache_dir, 'value', "").strip()
                if not cache_dir: cache_dir = DATA_DIR
                os.makedirs(cache_dir, exist_ok=True)
                backup_file_path = os.path.join(cache_dir, "Devotional_Backup.txt")

                try:
                    with open(backup_file_path, "w", encoding="utf-8") as bf:
                        bf.write(backup_str)
                    file_status_text.value = f"✅ Auto-saved to:\n{backup_file_path}"
                except Exception as ex:
                    file_status_text.value = f"⚠️ Could not save file: {ex}"

                try:
                    backup_field.update()
                    file_status_text.update()
                except: pass

            def copy_backup(e):
                if not backup_field.value: return show_snack("Nothing to copy!", "orange")
                try:
                    if hasattr(page, 'set_clipboard'): page.set_clipboard(backup_field.value)
                    else:
                        import pyperclip
                        pyperclip.copy(backup_field.value)
                    show_snack("Backup code copied to clipboard!", "green")
                except Exception:
                    show_snack("Auto-copy unavailable. Please manually select and copy the text.", "orange")

            chk_settings.on_change = generate_backup_str
            chk_favorites.on_change = generate_backup_str

            generate_backup_str()

            dlg = ft.AlertDialog(
                title=ft.Text("Backup & Sync Data"),
                content=ft.Column([
                    ft.Text("Select what to backup:", weight="bold", size=12),
                    chk_settings,
                    chk_favorites,
                    ft.Divider(height=5),
                    file_status_text,
                    ft.Text("To sync across devices, copy this file via Google Drive/USB to your other device's Cache folder.\n\nOr manually copy the code below:", size=11, color="grey300"),
                    backup_field
                ], tight=True),
                actions=[
                    ft.TextButton("📋 Copy Code", on_click=copy_backup, style=ft.ButtonStyle(color="blue400")),
                    ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))
                ]
            )
            show_dialog(dlg)
        except Exception as ex: show_snack(f"Failed to create backup: {ex}", "red")

    def perform_restore(e):
        try:
            chk_restore_settings = ft.Checkbox(label="Restore Settings & API Keys", value=True)
            chk_restore_favorites = ft.Checkbox(label="Restore Favorites", value=True)
            restore_field = ft.TextField(label="Paste backup code here...", multiline=True, min_lines=4, max_lines=8)

            def process_data(restored_data):
                if not chk_restore_settings.value and not chk_restore_favorites.value:
                    return show_snack("Please select what to restore!", "orange")

                restored_count = 0
                if chk_restore_favorites.value and "favorites" in restored_data:
                    favorites.clear()
                    favorites.extend(restored_data["favorites"])
                    save_favorites()
                    refresh_fav_list()
                    restored_count += 1

                if chk_restore_settings.value:
                    keys_mapping = [
                        ("format", dd_format), ("style", dd_style), ("version", dd_version),
                        ("theme", dd_theme), ("length", dd_length), ("lang", dd_lang),
                        ("duration", dd_duration), ("font", dd_font), ("size", dd_size),
                        ("model", dd_model), ("backend", dd_backend), ("tiktok_voice", dd_tiktok_voice),
                        ("voicebox_engine", dd_voicebox_engine), ("tts_engine", dd_tts_engine),
                        ("sync_engine", dd_sync_engine), ("whisper_model", dd_whisper_model), ("edge_voice", dd_edge_voice)
                    ]
                    for key, control in keys_mapping:
                        if key in restored_data: control.value = restored_data[key]

                    text_mapping = [
                        ("tiktok_session_id", tf_tiktok_session), ("voicebox_url", tf_voicebox_url),
                        ("voicebox_preset", tf_voicebox_preset), ("fish_url", tf_fish_url),
                        ("audio_cache_dir", tf_cache_dir),
                        ("ninerouter_url", tf_9router_url), ("custom_model", tf_custom_model)
                    ]
                    for key, control in text_mapping:
                        if key in restored_data: control.value = restored_data[key]

                    check_mapping = [
                        ("autoplay", chk_autoplay), ("force_cache", chk_force_cache), ("safe_audio", chk_safe_audio),
                        ("highlight", chk_highlight), ("autoscroll", chk_autoscroll), ("auto_heal", chk_autoheal)
                    ]
                    for key, control in check_mapping:
                        if key in restored_data: control.value = restored_data[key]

                    if "scroll_speed" in restored_data:
                        try: scroll_speed_slider.value = max(0, min(40, float(restored_data["scroll_speed"])))
                        except Exception: pass
                        slider_label.value = f"{(scroll_speed_slider.value - 20) * 0.1:+.1f}s"

                    if "groq_keys" in restored_data:
                        groq_backend.keys = restored_data["groq_keys"]
                        groq_backend.save_keys(groq_backend.keys)
                    if "gemini_keys" in restored_data:
                        gemini_backend.keys = restored_data["gemini_keys"]
                        gemini_backend.save_keys(gemini_backend.keys)
                    if "openai_keys" in restored_data:
                        openai_backend.keys = restored_data["openai_keys"]
                        openai_backend.save_keys(openai_backend.keys)
                    if "claude_keys" in restored_data:
                        claude_backend.keys = restored_data["claude_keys"]
                        claude_backend.save_keys(claude_backend.keys)
                    if "ninerouter_keys" in restored_data:
                        nine_backend.keys = restored_data["ninerouter_keys"]
                        nine_backend.save_keys(nine_backend.keys)

                    if "elevenlabs_presets" in restored_data: app_settings["elevenlabs_presets"] = restored_data["elevenlabs_presets"]
                    if "elevenlabs_active_preset" in restored_data: dd_elevenlabs_preset.value = restored_data["elevenlabs_active_preset"]
                    if "fish_presets" in restored_data: app_settings["fish_presets"] = restored_data["fish_presets"]
                    if "fish_active_preset" in restored_data: dd_fish_preset.value = restored_data["fish_active_preset"]

                    update_font()
                    apply_backend_models(True)
                    save_app_settings()
                    refresh_el_dropdown()
                    refresh_fish_dropdown()
                    restored_count += 1

                hide_dialog(dlg)
                if restored_count > 0: show_snack("Selected data synced & restored successfully!", "green")
                else: show_snack("No matching data found in backup.", "orange")
                page.update()

            def process_restore_text(e):
                try:
                    val = restore_field.value or ""
                    if not val.strip(): return show_snack("Please paste a backup code first.", "orange")
                    restored_data = json.loads(val.strip())
                    process_data(restored_data)
                except json.JSONDecodeError:
                    show_snack("Invalid backup text format! Not valid JSON.", "red")
                except Exception as ex:
                    show_snack(f"Restore Error: {ex}", "red")

            def process_restore_file(e):
                cache_dir = getattr(tf_cache_dir, 'value', "").strip()
                if not cache_dir: cache_dir = DATA_DIR
                backup_file_path = os.path.join(cache_dir, "Devotional_Backup.txt")
                if os.path.exists(backup_file_path):
                    try:
                        with open(backup_file_path, "r", encoding="utf-8") as bf: restored_data = json.load(bf)
                        process_data(restored_data)
                    except json.JSONDecodeError:
                        show_snack("Invalid backup file format! Not valid JSON.", "red")
                    except Exception as ex: show_snack(f"Error reading file: {ex}", "red")
                else: show_snack(f"No Devotional_Backup.txt found in:\n{cache_dir}", "orange")

            dlg = ft.AlertDialog(
                title=ft.Text("Restore / Sync Data"),
                content=ft.Column([
                    ft.Text("Select what to restore:", weight="bold", size=12),
                    chk_restore_settings, chk_restore_favorites, ft.Divider(height=5),
                    ft.Text("Load from 'Devotional_Backup.txt' in your Cache Folder:", size=11, color="grey300"),
                    ft.TextButton("📂 Sync from File", on_click=process_restore_file, style=ft.ButtonStyle(bgcolor="blue700", color="white")),
                    ft.Divider(),
                    ft.Text("Or paste your backup code manually below:", size=11, color="grey300"),
                    restore_field
                ], tight=True),
                actions=[
                    ft.TextButton("Restore from Text", on_click=process_restore_text, style=ft.ButtonStyle(bgcolor="green", color="white")),
                    ft.TextButton("Cancel", on_click=lambda e: hide_dialog(dlg))
                ]
            )
            show_dialog(dlg)
        except Exception as gen_err:
            show_snack(f"Error opening restore window: {gen_err}", "red")

    pr = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
    status_text = ft.Text("Ready", color="grey400", size=12)
    is_processing = [False]

    def set_loading(is_loading, msg="Ready", is_rendering_audio=False):
        is_processing[0] = is_loading
        pr.visible = is_loading
        status_text.value = msg

        generate_btn.disabled = is_loading
        prompt_gen_btn.disabled = is_loading
        revise_btn.disabled = is_loading
        prompt_rev_btn.disabled = is_loading
        translate_btn.disabled = is_loading
        qa_btn.disabled = is_loading
        chk_safe_audio.disabled = is_loading

        if not is_audio_playing[0]:
            if is_rendering_audio:
                tts_btn.disabled = False
                tts_btn.text = "⏹️ Cancel Render"
                tts_btn.style = ft.ButtonStyle(bgcolor="red700", color="white", shape=ft.RoundedRectangleBorder(radius=8))

                top_play_btn.disabled = False
                top_play_btn.text = "⏹️"
            else:
                tts_btn.disabled = is_loading
                tts_btn.text = "🔊 Read Aloud"
                tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color="white", shape=ft.RoundedRectangleBorder(radius=8))

                top_play_btn.disabled = is_loading
                top_play_btn.text = "▶️"

            top_rec_btn.disabled = is_loading
            chk_autoplay.disabled = is_loading
            chk_force_cache.disabled = is_loading
            el_manage_btn.disabled = is_loading
            fish_manage_btn.disabled = is_loading
            link_audio_btn.disabled = is_loading

        try: page.update()
        except: pass

    def safe_fire_scroll(key=None, offset=None):
        """Scrolls to the REAL on-screen position of a control (by key), or to a pixel offset."""
        def _do():
            if key is not None:
                return reading_column.scroll_to(key=key, duration=300)
            return reading_column.scroll_to(offset=offset, duration=300)

        async def _execute_scroll():
            try:
                res = _do()
                if inspect.iscoroutine(res):
                    await res
            except Exception: pass

        if hasattr(page, 'run_task'):
            try:
                page.run_task(_execute_scroll)
                return
            except Exception: pass
        try:
            res = _do()
            if inspect.iscoroutine(res):
                asyncio.run(res)
        except Exception: pass

    def paint_unit(i, color):
        try:
            ctrls = reading_state["ctrls"]
            if 0 <= i < len(ctrls):
                ctrls[i].color = color
                ctrls[i].update()
        except Exception: pass

    def save_app_settings(e=None):
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r') as f: data = json.load(f)
                except Exception: pass

            if hasattr(dd_format, 'value'): data["format"] = dd_format.value
            if hasattr(dd_style, 'value'): data["style"] = dd_style.value
            if hasattr(dd_version, 'value'): data["version"] = dd_version.value
            if hasattr(dd_theme, 'value'): data["theme"] = dd_theme.value
            if hasattr(dd_length, 'value'): data["length"] = dd_length.value
            if hasattr(dd_lang, 'value'): data["lang"] = dd_lang.value
            if hasattr(dd_duration, 'value'): data["duration"] = dd_duration.value
            if hasattr(dd_font, 'value'): data["font"] = dd_font.value
            if hasattr(dd_size, 'value'): data["size"] = dd_size.value
            if hasattr(dd_model, 'value'): data["model"] = dd_model.value
            if hasattr(dd_backend, 'value'): data["backend"] = dd_backend.value
            data["custom_model"] = (tf_custom_model.value or "").strip()
            data["ninerouter_url"] = (tf_9router_url.value or "").strip()
            if app_settings.get("working_models"): data["working_models"] = app_settings["working_models"]
            data["auto_heal"] = chk_autoheal.value
            if hasattr(dd_tts_engine, 'value'): data["tts_engine"] = dd_tts_engine.value
            if hasattr(tf_tiktok_session, 'value'): data["tiktok_session_id"] = (tf_tiktok_session.value or "").strip()
            if hasattr(dd_tiktok_voice, 'value'): data["tiktok_voice"] = dd_tiktok_voice.value
            if hasattr(tf_voicebox_url, 'value'): data["voicebox_url"] = (tf_voicebox_url.value or "").strip()
            if hasattr(tf_voicebox_preset, 'value'): data["voicebox_preset"] = (tf_voicebox_preset.value or "").strip()
            if hasattr(dd_voicebox_engine, 'value'): data["voicebox_engine"] = dd_voicebox_engine.value
            if hasattr(tf_fish_url, 'value'): data["fish_url"] = (tf_fish_url.value or "").strip()
            if hasattr(chk_autoplay, 'value'): data["autoplay"] = chk_autoplay.value
            if hasattr(chk_force_cache, 'value'): data["force_cache"] = chk_force_cache.value
            if hasattr(chk_safe_audio, 'value'): data["safe_audio"] = chk_safe_audio.value
            data["highlight"] = chk_highlight.value
            data["autoscroll"] = chk_autoscroll.value
            data["sync_engine"] = dd_sync_engine.value
            data["whisper_model"] = dd_whisper_model.value
            data["edge_voice"] = dd_edge_voice.value
            if hasattr(scroll_speed_slider, 'value'): data["scroll_speed"] = scroll_speed_slider.value
            if hasattr(tf_cache_dir, 'value'): data["audio_cache_dir"] = tf_cache_dir.value
            if hasattr(dd_elevenlabs_preset, 'value') and dd_elevenlabs_preset.value: data["elevenlabs_active_preset"] = dd_elevenlabs_preset.value
            if hasattr(dd_fish_preset, 'value') and dd_fish_preset.value: data["fish_active_preset"] = dd_fish_preset.value
            if "elevenlabs_presets" in app_settings: data["elevenlabs_presets"] = app_settings["elevenlabs_presets"]
            if "fish_presets" in app_settings: data["fish_presets"] = app_settings["fish_presets"]

            try:
                current_val = text_area.value
                if current_val and not current_val.startswith("Welcome!"):
                    data["last_devotion_text"] = current_val
            except Exception: pass

            with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)
        except Exception as err:
            pass

    def on_text_changed(e):
        app_state["last_audio_path"] = ""
        app_state["last_audio_hash"] = ""
        save_app_settings()

    def browse_cache_dir(e):
        if is_android_sys():
            android_path = "/storage/emulated/0/Documents/DailyDevotional"
            try:
                os.makedirs(android_path, exist_ok=True)
                tf_cache_dir.value = android_path
                save_app_settings()
                try: tf_cache_dir.update()
                except: pass
                show_snack("Cache folder set to Android Documents!", "green")
            except Exception as ex:
                show_snack(f"Permission Denied. Could not create folder: {ex}", "red")
            return

        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            selected_dir = filedialog.askdirectory(
                parent=root,
                title="Select Offline Audio Cache Folder",
                initialdir=tf_cache_dir.value
            )
            root.destroy()

            if selected_dir:
                tf_cache_dir.value = selected_dir
                save_app_settings()
                try: tf_cache_dir.update()
                except: pass
        except Exception as ex:
            show_snack(f"Browse Error: {ex}", "red")

    def clear_cache_dir(e):
        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if os.path.exists(cache_dir):
            try:
                count = 0
                for f in os.listdir(cache_dir):
                    if f.lower().endswith(AUDIO_EXTS) or f.endswith(".align.json"):
                        os.remove(os.path.join(cache_dir, f))
                        count += 1
                show_snack(f"Cleared {count} orphaned audio cache files!", "green")
                page.update()
            except Exception as ex:
                show_snack(f"Error clearing cache: {ex}", "red")
                page.update()
        else:
            show_snack("Cache folder is already empty.", "orange")
            page.update()

    def open_el_dialog(e):
        el_list = ft.Column(spacing=5, height=150, scroll="auto")
        lbl_status = ft.Text("", color="cyan400", size=12)

        def refresh_el_list():
            el_list.controls.clear()
            presets = app_settings.get("elevenlabs_presets", {})
            for name, data in presets.items():
                k = data.get("api_key", "")
                masked_k = f"{k[:4]}...{k[-4:]}" if len(k) > 8 else "No Key"
                def make_delete(n): return lambda e: delete_el_preset(n)
                row = ft.Row([ft.Text(f"{name} ({masked_k})", expand=True, size=12), ft.TextButton("❌", on_click=make_delete(name), width=40)])
                el_list.controls.append(row)
            try: el_list.update()
            except: pass

        def delete_el_preset(name):
            try:
                presets = app_settings.get("elevenlabs_presets", {})
                if name in presets:
                    del presets[name]
                    app_settings["elevenlabs_presets"] = presets
                    save_app_settings()
                    refresh_el_dropdown()
                    refresh_el_list()
                    lbl_status.value = f"Preset '{name}' deleted."
                    lbl_status.color = "orange"
                    dlg.update()
            except Exception as ex:
                lbl_status.value = f"Delete Error: {ex}"
                lbl_status.color = "red"
                dlg.update()

        name_tf = ft.TextField(label="Preset Name (e.g. Account1)", height=40, value="")
        id_tf = ft.TextField(label="Voice ID", height=40, value="")
        key_tf = ft.TextField(label="API Key", password=True, height=40, value="")

        def add_el_preset(e):
            try:
                n = (name_tf.value or "").strip()
                vid = (id_tf.value or "").strip()
                k = (key_tf.value or "").strip()

                if not n or not vid or not k:
                    lbl_status.value = "Error: All fields are required."
                    lbl_status.color = "red"
                    dlg.update()
                    return

                presets = app_settings.get("elevenlabs_presets", {})
                presets[n] = {"voice_id": vid, "api_key": k}
                app_settings["elevenlabs_presets"] = presets
                save_app_settings()

                dd_elevenlabs_preset.options = [ft.dropdown.Option(opt) for opt in presets.keys()]
                if n in [opt.key for opt in dd_elevenlabs_preset.options]:
                    dd_elevenlabs_preset.value = n

                dd_elevenlabs_preset.update()

                name_tf.value = ""
                id_tf.value = ""
                key_tf.value = ""

                lbl_status.value = f"Preset '{n}' saved successfully!"
                lbl_status.color = "green"

                refresh_el_list()
                dlg.update()
                page.update()
            except Exception as ex:
                lbl_status.value = f"Error saving preset: {ex}"
                lbl_status.color = "red"
                dlg.update()

        dlg = ft.AlertDialog(
            title=ft.Text("ElevenLabs Presets"),
            content=ft.Column([
                ft.Text("Add multiple burner accounts. App auto-rotates if limits hit.", size=11, color="grey400"),
                el_list, name_tf, id_tf, key_tf,
                lbl_status,
                ft.TextButton("💾 Save Preset", on_click=add_el_preset, style=ft.ButtonStyle(bgcolor="green", color="white"))
            ], tight=True),
            actions=[ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        )
        refresh_el_list()
        show_dialog(dlg)

    def refresh_el_dropdown():
        try:
            presets = app_settings.get("elevenlabs_presets", {})
            dd_elevenlabs_preset.options = [ft.dropdown.Option(k) for k in presets.keys()]
            valid_keys = [opt.key for opt in dd_elevenlabs_preset.options]
            if dd_elevenlabs_preset.value not in valid_keys:
                dd_elevenlabs_preset.value = valid_keys[0] if valid_keys else None
            dd_elevenlabs_preset.update()
            page.update()
        except Exception as ex: pass

    def open_fish_dialog(e):
        fish_list = ft.Column(spacing=5, height=150, scroll="auto")
        lbl_status = ft.Text("", color="cyan400", size=12)

        def refresh_fish_list():
            fish_list.controls.clear()
            presets = app_settings.get("fish_presets", {})
            for name, data in presets.items():
                p_aud = data.get("audio", "")
                masked_p = f"...{p_aud[-15:]}" if len(p_aud) > 15 else p_aud
                def make_delete(n): return lambda e: delete_fish_preset(n)
                row = ft.Row([
                    ft.Text(f"{name} ({masked_p})", expand=True, size=12),
                    ft.TextButton("❌", on_click=make_delete(name), width=40)
                ])
                fish_list.controls.append(row)
            try: fish_list.update()
            except: pass

        def delete_fish_preset(name):
            try:
                presets = app_settings.get("fish_presets", {})
                if name in presets:
                    del presets[name]
                    app_settings["fish_presets"] = presets
                    save_app_settings()
                    refresh_fish_dropdown()
                    refresh_fish_list()
                    lbl_status.value = f"Fish Preset '{name}' deleted."
                    lbl_status.color = "orange"
                    dlg.update()
            except Exception as ex:
                lbl_status.value = f"Delete Error: {ex}"
                lbl_status.color = "red"
                dlg.update()

        fish_name_tf = ft.TextField(label="Preset Name (e.g. MyVoice)", height=40, value="")
        fish_audio_tf = ft.TextField(label="Ref Audio Path (.wav)", height=40, value="")
        fish_text_tf = ft.TextField(label="Ref Text Path (.txt) [Optional]", height=40, value="")

        def add_fish_preset(e):
            try:
                n = (fish_name_tf.value or "").strip()
                audio_path = (fish_audio_tf.value or "").strip().strip('"').strip("'")
                text_path = (fish_text_tf.value or "").strip().strip('"').strip("'")

                if not n or not audio_path:
                    lbl_status.value = "Error: Preset Name & Audio Path required."
                    lbl_status.color = "red"
                    dlg.update()
                    return

                presets = app_settings.get("fish_presets", {})
                presets[n] = {"audio": audio_path, "text": text_path}
                app_settings["fish_presets"] = presets
                save_app_settings()

                dd_fish_preset.options = [ft.dropdown.Option(opt) for opt in presets.keys()]
                if n in [opt.key for opt in dd_fish_preset.options]:
                    dd_fish_preset.value = n

                dd_fish_preset.update()
                fish_name_tf.value = ""
                fish_audio_tf.value = ""
                fish_text_tf.value = ""

                lbl_status.value = f"Preset '{n}' saved successfully!"
                lbl_status.color = "green"
                refresh_fish_list()
                dlg.update()
                page.update()
            except Exception as ex:
                lbl_status.value = f"Error saving preset: {ex}"
                lbl_status.color = "red"
                dlg.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Fish Speech Presets"),
            content=ft.Column([
                ft.Text("Paste local file paths to clone voices. (Shift+Right-Click file -> Copy as path)", size=11, color="grey400"),
                ft.Text("💡 Hint: Fish Speech clones the EXACT accent of your audio file.\nFor an American accent, use an American speaker's .wav!", size=11, color="amber400"),
                fish_list, fish_name_tf, fish_audio_tf, fish_text_tf,
                lbl_status,
                ft.TextButton("💾 Save Preset", on_click=add_fish_preset, style=ft.ButtonStyle(bgcolor="green", color="white"))
            ], tight=True),
            actions=[ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        )
        refresh_fish_list()
        show_dialog(dlg)

    def refresh_fish_dropdown():
        try:
            presets = app_settings.get("fish_presets", {})
            dd_fish_preset.options = [ft.dropdown.Option(k) for k in presets.keys()]
            valid_keys = [opt.key for opt in dd_fish_preset.options]
            if dd_fish_preset.value not in valid_keys:
                dd_fish_preset.value = valid_keys[0] if valid_keys else None
            dd_fish_preset.update()
            page.update()
        except Exception as ex: pass

    def test_voicebox_conn(e):
        url = (tf_voicebox_url.value or "").strip().rstrip('/')
        if not url: return show_snack("Please enter a Voicebox URL first.", "red")
        if is_android_sys() and ("127.0.0.1" in url or "localhost" in url):
            return show_error_dialog("⚠️ You cannot use 127.0.0.1 or localhost on a phone!\n\nThat points to the phone itself. You must use your PC's actual Wi-Fi IP Address (e.g., http://192.168.1.5:17493).")

        set_loading(True, "Testing connection...")
        def worker():
            try:
                res = requests.get(f"{url}/profiles", timeout=5)
                def update_ui():
                    set_loading(False)
                    if res.status_code == 200:
                        data = res.json()
                        count = len(data) if isinstance(data, list) else len(data.get("items", []))
                        show_snack(f"✅ Success! Connected to Voicebox ({count} voices found).", "green")
                    else:
                        show_snack(f"⚠️ Connected, but API returned status {res.status_code}.", "orange")
                ui_call(update_ui)
            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"❌ Connection Error: {ex}", "red")
                ui_call(handle_err)

        threading.Thread(target=worker, daemon=True).start()

    def on_slider_change(e=None):
        try:
            v = float(scroll_speed_slider.value)
            slider_label.value = f"{(v - 20) * 0.1:+.1f}s"
            slider_label.update()
        except Exception: pass
        save_app_settings()

    for dd in [dd_format, dd_style, dd_theme, dd_length, dd_lang, dd_duration, dd_tts_engine, chk_autoplay, chk_force_cache, chk_safe_audio, tf_tiktok_session, dd_tiktok_voice, tf_voicebox_url, tf_voicebox_preset, dd_voicebox_engine, dd_elevenlabs_preset, dd_fish_preset, tf_fish_url, chk_autoscroll, dd_sync_engine, dd_whisper_model, dd_edge_voice, tf_custom_model, tf_9router_url, chk_autoheal]:
        dd.on_change = save_app_settings
    scroll_speed_slider.on_change = on_slider_change

    def update_font(e=None):
        family = dd_font.value if dd_font.value != "Default" else None
        try: size = int(dd_size.value)
        except (ValueError, TypeError): size = 16

        text_area.text_size = size
        fav_text_area.text_size = size
        reading_text.size = size
        reading_text.font_family = family

        try:
            ts = ft.TextStyle(size=size, font_family=family) if family else ft.TextStyle(size=size)
            text_area.text_style = ts
            fav_text_area.text_style = ts
            reading_text.style = ts
        except Exception:
            pass

        if e is not None:
            save_app_settings()
            try:
                text_area.update()
                fav_text_area.update()
                page.update()
                show_snack(f"Font updated to {dd_font.value} (Size {size})", "green")
            except Exception: pass

    dd_font.on_change = update_font
    dd_size.on_change = update_font

    def get_active_backend():
        b = dd_backend.value or "Groq"
        if b == "LM Studio (Local)": be = lmstudio_backend
        elif b == "Gemini": be = gemini_backend
        elif b == "OpenAI": be = openai_backend
        elif b.startswith("Claude"): be = claude_backend
        elif b.startswith("9Router"):
            nine_backend.endpoint = normalize_9router_base(tf_9router_url.value) + "/chat/completions"
            be = nine_backend
        else: be = groq_backend
        be.auto_heal = bool(chk_autoheal.value)
        be.heal_pool = list((app_settings.get("working_models") or {}).get(b) or BACKEND_MODELS.get(b, []))
        return be

    def current_model():
        return (tf_custom_model.value or "").strip() or (dd_model.value or "")

    def apply_backend_models(keep_model=True):
        """Fills the model list (only models that passed a live test, once tested) and drops retired saved ones."""
        b = dd_backend.value or "Groq"
        models = list((app_settings.get("working_models") or {}).get(b) or BACKEND_MODELS.get(b, ["local-model"]))
        dd_model.options = [ft.dropdown.Option(x) for x in models]
        if not (keep_model and dd_model.value in models):
            dd_model.value = models[0]
        tf_9router_url.visible = b.startswith("9Router")
        try: page.update()
        except Exception: pass

    def on_backend_change(e):
        tf_custom_model.value = ""          # a custom name belongs to the previous provider
        apply_backend_models(keep_model=False)
        save_app_settings()

    def on_model_change(e):
        save_app_settings()

    def show_info_dialog(title, msg):
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.TextField(value=msg, multiline=True, read_only=True, min_lines=8, max_lines=16, text_size=11),
            actions=[ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))])
        show_dialog(dlg)

    def note_heal(backend):
        """Called after a request: if auto-heal switched models, make the new one the selected model."""
        m = getattr(backend, "healed_to", None)
        if not m:
            return
        backend.healed_to = None
        tf_custom_model.value = ""
        if m not in [o.key for o in dd_model.options]:
            dd_model.options.append(ft.dropdown.Option(m))
        dd_model.value = m
        save_app_settings()
        show_snack(f"🩹 Auto-healed: the previous model failed, now using {m}", "blue")
        try:
            dd_model.update(); tf_custom_model.update()
        except Exception: pass

    def test_and_fix_models(e=None):
        """Finds the provider's live models, TESTS each with a tiny request, and lists only the ones that work."""
        if is_processing[0]: return
        b = dd_backend.value or "Groq"
        backend = get_active_backend()
        kind = backend.kind
        endpoint = getattr(backend, "endpoint", None)
        if b.startswith("9Router") and is_android_sys() and ("localhost" in (endpoint or "") or "127.0.0.1" in (endpoint or "")):
            return show_error_dialog("On a phone, 'localhost' is the phone itself.\n\nRun 9Router on your PC with HOSTNAME=0.0.0.0 and use your PC's Wi-Fi IP in the 9Router URL, e.g. http://192.168.1.5:20128/v1")
        key = backend._first_key()
        if kind not in ("lmstudio", "ninerouter") and not key:
            return show_snack("Add an API key first (🔑 button), then press Test & Fix Models.", "red")
        set_loading(True, "Finding models...")

        def worker():
            try:
                static = list(BACKEND_MODELS.get(b, []))
                live = discover_models(kind, key, endpoint)
                cand = []
                for m in static + live:
                    if m and m not in cand and (m in static or not is_costly_model(m)):
                        cand.append(m)
                cand = cand[:48 if kind == "ninerouter" else 14]
                if not cand:
                    raise Exception("No models were returned. Is the provider reachable (and 9Router running with a provider connected)?")

                def prog(d, t, g):
                    ui_call(lambda: (set_loading(True, f"Testing models {d}/{t} - {g} working..."), page.update()))

                good, bad = probe_many(kind, cand, key, endpoint, workers=6 if kind == "ninerouter" else 4, progress=prog)

                def done():
                    set_loading(False)
                    labels = {"exhausted": "❌ Exhausted / rate-limited", "dead": "❌ Retired / not found / unsupported",
                              "auth": "❌ Key rejected", "down": "❌ Not responding", "net": "❌ Network error"}
                    groups = {}
                    for m, (st, det) in bad.items():
                        groups.setdefault(st, []).append(m)
                    tail = ""
                    for st, ms in groups.items():
                        tail += f"\n\n{labels.get(st, st)} ({len(ms)}): " + ", ".join(ms[:15]) + (" ..." if len(ms) > 15 else "")
                    if good:
                        wm = app_settings.setdefault("working_models", {})
                        wm[b] = [m for m, _ in good]
                        apply_backend_models(keep_model=True)
                        save_app_settings()
                        body = "✅ Working right now (fastest first):\n" + "\n".join(f"  {m}   {dt:.1f}s" for m, dt in good[:30]) + tail
                        show_info_dialog(f"{len(good)} of {len(cand)} models work", body)
                    else:
                        show_info_dialog("No working model found", "None of the tested models answered." + tail +
                                         "\n\nYour previous list was kept. Check your key / credits, or connect another provider.")
                ui_call(done)
            except Exception as ex:
                def bad_():
                    set_loading(False)
                    show_error_dialog(f"Model test failed:\n{ex}")
                ui_call(bad_)

        threading.Thread(target=worker, daemon=True).start()

    dd_backend.on_change = on_backend_change
    dd_model.on_change = on_model_change
    btn_heal_models.on_click = test_and_fix_models

    def schedule_autoplay():
        if chk_autoplay.value:
            threading.Timer(0.5, lambda: ui_call(on_play_tts)).start()

    def apply_new_text(new_text, ok_msg):
        text_area.value = format_and_clean(new_text)
        reading_text.value = text_area.value
        save_app_settings()
        show_snack(ok_msg, "green")
        try:
            text_area.update()
            text_container_gen.update()
            page.update()
        except Exception: pass

    def on_apply_verse(e=None):
        try:
            save_app_settings()
            if is_processing[0]: return
            content = text_area.value

            if not content or content.startswith("Welcome!"):
                if e is not None:
                    show_snack("Generate a devotional first before changing the Bible version.", "orange")
                return

            set_loading(True, "Translating Verse...")
            version_val = dd_version.value
            model_val = current_model()
            fmt_val = dd_format.value
            backend = get_active_backend()

            def worker():
                try:
                    success, new_content = backend.revise_verse(content, version_val, model_val, fmt_val)

                    def update_ui():
                        set_loading(False)
                        note_heal(backend)
                        if success:
                            apply_new_text(new_content, "Verse translated successfully!")
                            schedule_autoplay()
                        else:
                            show_error_dialog(new_content)
                            show_snack("Error applying Bible version.", "red")
                            page.update()

                    ui_call(update_ui)

                except Exception as ex:
                    def handle_err():
                        set_loading(False)
                        show_snack(f"Translation error: {ex}", "red")
                        page.update()
                    ui_call(handle_err)

            threading.Thread(target=worker, daemon=True).start()
        except Exception as ex:
            log_error(f"Apply verse error: {ex}")

    def execute_generation(custom_instruction=""):
        if is_processing[0]: return
        set_loading(True, f"Generating {dd_format.value}...")

        style_val, ver_val, theme_val, len_val, lang_val, model_val, dur_val, fmt_val = dd_style.value, dd_version.value, dd_theme.value, dd_length.value, dd_lang.value, current_model(), dd_duration.value, dd_format.value
        backend = get_active_backend()

        def worker():
            try:
                success, content = backend.generate_devotional(style_val, ver_val, theme_val, len_val, lang_val, custom_instruction, model_val, dur_val, fmt_val)

                def update_ui():
                    set_loading(False)
                    note_heal(backend)
                    if success:
                        apply_new_text(content, "Content generated successfully!")
                        schedule_autoplay()
                    else:
                        show_error_dialog(content)
                        show_snack("Failed to generate.", "red")
                        page.update()

                ui_call(update_ui)

            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"Generation error: {ex}", "red")
                    page.update()
                ui_call(handle_err)

        threading.Thread(target=worker, daemon=True).start()

    def on_generate(e): execute_generation()

    def open_generate_ai_dialog(e):
        prompt_field = ft.TextField(label="Custom Instruction (e.g., 'Focus on strength')")
        def submit_dlg(e):
            hide_dialog(dlg)
            if prompt_field.value and prompt_field.value.strip(): execute_generation(prompt_field.value.strip())

        dlg = ft.AlertDialog(
            title=ft.Text("Generate with AI Prompt"), content=prompt_field,
            actions=[ft.TextButton("Cancel", on_click=lambda e: hide_dialog(dlg)), ft.TextButton("Generate", on_click=submit_dlg, style=ft.ButtonStyle(bgcolor="blue", color="white"))]
        )
        show_dialog(dlg)

    def execute_revision(custom_instruction=""):
        if is_processing[0]: return
        content = text_area.value
        if not content or content.startswith("Welcome!"): return show_snack("Please generate a document first.", "red")

        set_loading(True, "Revising content...")
        style_val, len_val, lang_val, model_val, fmt_val = dd_style.value, dd_length.value, dd_lang.value, current_model(), dd_format.value
        backend = get_active_backend()

        def worker():
            try:
                success, new_content = backend.revise_reflection(content, style_val, len_val, lang_val, custom_instruction, model_val, fmt_val)

                def update_ui():
                    set_loading(False)
                    note_heal(backend)
                    if success:
                        apply_new_text(new_content, "Content revised successfully!")
                        schedule_autoplay()
                    else:
                        show_error_dialog(new_content)
                        show_snack("Failed to revise content.", "red")
                        page.update()

                ui_call(update_ui)

            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"Revision error: {ex}", "red")
                    page.update()
                ui_call(handle_err)

        threading.Thread(target=worker, daemon=True).start()

    def on_revise_standard(e): execute_revision()

    def open_revise_ai_dialog(e):
        prompt_field = ft.TextField(label="Custom Instruction (e.g., 'Make it a short story')")
        def submit_dlg(e):
            hide_dialog(dlg)
            if prompt_field.value and prompt_field.value.strip(): execute_revision(prompt_field.value.strip())

        dlg = ft.AlertDialog(
            title=ft.Text("Revise Content with Prompt"), content=prompt_field,
            actions=[ft.TextButton("Cancel", on_click=lambda e: hide_dialog(dlg)), ft.TextButton("Revise", on_click=submit_dlg, style=ft.ButtonStyle(bgcolor="blue", color="white"))]
        )
        show_dialog(dlg)

    def on_generate_qa(e=None):
        if is_processing[0]: return
        content = text_area.value
        if not content or content.startswith("Welcome!"): return show_snack("Please generate a document first.", "red")

        set_loading(True, "Generating Q&A...")
        lang_val, model_val, fmt_val = dd_lang.value, current_model(), dd_format.value
        backend = get_active_backend()

        def worker():
            try:
                success, qa_content = backend.generate_qa(content, lang_val, "", model_val, fmt_val)

                def update_ui():
                    set_loading(False)
                    note_heal(backend)
                    if success:
                        text_area.value = content.strip() + "\n\n---\n\n" + qa_content.strip()
                        reading_text.value = text_area.value
                        save_app_settings()
                        show_snack("Q&A generated successfully!", "green")
                        try:
                            text_area.update()
                            text_container_gen.update()
                            page.update()
                        except Exception: pass
                    else:
                        show_error_dialog(qa_content)
                        show_snack("Failed to generate Q&A.", "red")
                        page.update()

                ui_call(update_ui)

            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"Q&A error: {ex}", "red")
                    page.update()
                ui_call(handle_err)

        threading.Thread(target=worker, daemon=True).start()

    def on_play_tts(e=None, record_video=False):
        if app_state.get("is_rendering_audio"):
            app_state["cancel_render"] = True
            app_state["is_rendering_audio"] = False
            show_snack("Render canceled. Cleaning up...", "orange")
            def _reset():
                set_loading(False)
                page.update()
            ui_call(_reset)
            return

        if is_audio_playing[0]:
            try:
                if PYGAME_AVAILABLE and not is_android_sys() and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                elif audio_player:
                    audio_player.pause()

                is_audio_playing[0] = False
                is_video_recording[0] = False
                tts_btn.text = "🔊 Read Aloud"
                tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color="white", shape=ft.RoundedRectangleBorder(radius=8))
                top_play_btn.text = "▶️"
                top_rec_btn.style = ft.ButtonStyle(color="red400")
                top_rec_btn.text = "⏺️ Rec"

                if current_fullscreen_mode[0] == "none":
                    reading_container.border = make_border(1.5, "blue600")

                text_container_gen.content = text_area

                try:
                    tts_btn.update()
                    top_play_btn.update()
                    top_rec_btn.update()
                    text_container_gen.update()
                except Exception: pass
                show_snack("Audio stopped.", "orange")
                page.update()
            except Exception as e: log_error(f"Error stopping audio: {e}")
            return

        if is_processing[0]: return

        content = text_area.value.strip()

        if not content or content.startswith("Welcome!"):
            show_snack("Please generate text to read first.", "red")
            return

        engine = dd_tts_engine.value
        session_id = (tf_tiktok_session.value or "").strip()
        voice_id = TIKTOK_VOICES.get(dd_tiktok_voice.value, "en_us_002")
        server_url = (tf_voicebox_url.value or "").strip()
        preset = (tf_voicebox_preset.value or "").strip()
        vb_engine = dd_voicebox_engine.value

        el_presets = app_settings.get("elevenlabs_presets", {})
        el_active_preset = getattr(dd_elevenlabs_preset, 'value', "")

        fish_presets = app_settings.get("fish_presets", {})
        fish_active_preset = getattr(dd_fish_preset, 'value', "")
        fish_url = (tf_fish_url.value or "").strip()

        if engine == "TikTok API" and not session_id and not chk_force_cache.value: return show_snack("Missing TikTok Session ID! Enter it in settings.", "red")
        if engine == "Local PC Voicebox" and not server_url and not chk_force_cache.value: return show_snack("Missing Voicebox URL! Enter your PC's IP URL in settings.", "red")
        if engine == "ElevenLabs" and not el_presets and not chk_force_cache.value: return show_snack("Missing ElevenLabs Settings! Please click 'Manage ElevenLabs Keys' below.", "red")
        if engine == "Fish Speech" and not fish_presets and not chk_force_cache.value: return show_snack("Missing Fish Speech Settings! Please configure a preset.", "red")

        if not chk_force_cache.value and is_android_sys() and engine in ["Local PC Voicebox", "Fish Speech"] and ("127.0.0.1" in server_url or "localhost" in server_url or "127.0.0.1" in fish_url or "localhost" in fish_url):
            return show_error_dialog("⚠️ You cannot use 127.0.0.1 or localhost on a phone!\n\nThat points to the phone itself. You must use your PC's actual Wi-Fi IP Address (e.g., http://192.168.1.5:8080).")

        app_state["is_rendering_audio"] = True
        app_state["cancel_render"] = False
        my_render_id = time.time()
        app_state["current_render_id"] = my_render_id

        set_loading(True, f"Generating {engine} Audio...", is_rendering_audio=True)

        fingerprint = f"{content}_{engine}_{session_id}_{voice_id}_{server_url}_{preset}_{vb_engine}_{el_active_preset}_{fish_active_preset}_{fish_url}_{dd_edge_voice.value}"
        content_hash = hashlib.md5(fingerprint.encode('utf-8')).hexdigest()

        pure_text_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        app_state["last_audio_hash"] = pure_text_hash

        def worker():
            try:
                for f in os.listdir(DATA_DIR):
                    if f.startswith("tts_output_") or f.startswith("play_") or f.startswith("temp_video_") or f.startswith("temp_final_"):
                        try: os.remove(os.path.join(DATA_DIR, f))
                        except: pass

                output_file = f"tts_output_{int(my_render_id)}.mp3"
                output_path = os.path.join(DATA_DIR, output_file)

                cache_dir = getattr(tf_cache_dir, 'value', "").strip()
                if not cache_dir: cache_dir = DATA_DIR
                os.makedirs(cache_dir, exist_ok=True)

                cached_mp3 = os.path.join(cache_dir, f"{content_hash}.mp3")
                cached_wav = os.path.join(cache_dir, f"{content_hash}.wav")
                pure_mp3 = os.path.join(cache_dir, f"{pure_text_hash}.mp3")
                pure_wav = os.path.join(cache_dir, f"{pure_text_hash}.wav")

                is_cached = False
                is_silent_playback = False
                reset_holder = {"c": None}

                linked_audio = find_cached_audio(cache_dir, pure_text_hash)
                if linked_audio:
                    success, result, output_path = True, "Loaded from linked audio", linked_audio
                    output_file = os.path.basename(linked_audio)
                    is_cached = True
                elif os.path.exists(cached_mp3):
                    success, result, output_path = True, "Loaded from cache", cached_mp3
                    output_file = os.path.basename(cached_mp3)
                    is_cached = True
                elif os.path.exists(cached_wav):
                    success, result, output_path = True, "Loaded from cache", cached_wav
                    output_file = os.path.basename(cached_wav)
                    is_cached = True
                elif chk_force_cache.value:
                    def _notify_silent():
                        show_snack("No cache found for this text. Auto-scrolling silently.", "orange")
                    ui_call(_notify_silent)

                    success, result, output_path = True, "Silent Playback", ""
                    is_silent_playback = True
                else:
                    cancel_check = lambda: app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id

                    def _update_status(msg):
                        if cancel_check(): return
                        def _update():
                            set_loading(True, msg, is_rendering_audio=True)
                            page.update()
                        ui_call(_update)

                    if engine == "TikTok API":
                        success, result = generate_tiktok_audio(content, voice_id, session_id, output_path)
                    elif engine == "Edge TTS (Free)":
                        success, result = generate_edge_audio(content, EDGE_VOICES.get(dd_edge_voice.value, "en-US-AriaNeural"), output_path)
                    elif engine == "Local PC Voicebox":
                        output_file = output_file.replace(".mp3", ".wav")
                        output_path = output_path.replace(".mp3", ".wav")
                        success, result = generate_voicebox_audio(content, server_url, preset, vb_engine, output_path, status_callback=_update_status, cancel_callback=cancel_check)
                    elif engine == "Fish Speech":
                        output_file = output_file.replace(".mp3", ".wav")
                        output_path = output_path.replace(".mp3", ".wav")
                        success, result, successful_preset_name = generate_fish_speech_audio(content, fish_url, fish_presets, fish_active_preset, output_path, status_callback=_update_status, cancel_callback=cancel_check)
                        if success:
                            def _update_preset():
                                dd_fish_preset.value = successful_preset_name
                                save_app_settings()
                                try: dd_fish_preset.update()
                                except: pass
                            ui_call(_update_preset)
                    else:
                        success, result, successful_preset_name = generate_elevenlabs_audio(content, el_presets, el_active_preset, output_path)
                        if success:
                            def _update_preset():
                                dd_elevenlabs_preset.value = successful_preset_name
                                save_app_settings()
                                try: dd_elevenlabs_preset.update()
                                except: pass
                            ui_call(_update_preset)

                    if app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id:
                        try:
                            if os.path.exists(output_path): os.remove(output_path)
                        except: pass
                        return

                    if success and not is_silent_playback:
                        app_state["last_audio_path"] = output_path

                        if not is_cached:
                            try:
                                if os.path.exists(output_path):
                                    ext = os.path.splitext(output_path)[1].lower() or ".mp3"
                                    cache_path_specific = os.path.join(cache_dir, f"{content_hash}{ext}")
                                    cache_path_pure = os.path.join(cache_dir, f"{pure_text_hash}{ext}")
                                    shutil.copy2(output_path, cache_path_specific)
                                    shutil.copy2(output_path, cache_path_pure)
                                    print(f"✅ Auto-Cached audio to {cache_path_pure}")
                            except Exception as e:
                                log_error(f"Cache Error: {e}")

                # --- RESET VOICE BUTTON (shown under the text while reading) ---
                if success and not is_silent_playback:
                    def purge_current_cache_and_retry(e):
                        try:
                            if PYGAME_AVAILABLE and not is_android_sys() and pygame.mixer.get_init():
                                pygame.mixer.music.stop()
                                try: pygame.mixer.music.unload()
                                except: pass
                            elif audio_player:
                                audio_player.pause()
                                audio_player.src = None
                                page.update()

                            for ext in AUDIO_EXTS:
                                p1 = os.path.join(cache_dir, f"{content_hash}{ext}")
                                p2 = os.path.join(cache_dir, f"{pure_text_hash}{ext}")
                                if os.path.exists(p1): os.remove(p1)
                                if os.path.exists(p2): os.remove(p2)

                            show_snack("🔄 Cache cleared! Ready to render with a different voice.", "blue")
                            app_state["last_audio_path"] = ""
                            app_state["last_audio_hash"] = ""

                            on_play_tts(None)
                        except Exception as ex:
                            show_snack(f"Wipe failed: {ex}", "red")

                    reset_holder["c"] = ft.Container(
                        content=ft.ElevatedButton(
                            "🔄 Reset Voice",
                            on_click=purge_current_cache_and_retry,
                            style=ft.ButtonStyle(bgcolor="red700", color="white")
                        ),
                        padding=make_padding(top=20),
                        alignment=center_alignment()
                    )

                if success:
                    if output_path and os.path.exists(output_path) and os.path.getsize(output_path) < 100:
                        def _warn():
                            show_snack("⚠️ Warning: Server returned an empty audio file (Silence).", "orange")
                            set_loading(False)
                            page.update()
                        ui_call(_warn)
                        return

                    try:
                        temp_avi_path = os.path.join(DATA_DIR, f"temp_video_{int(time.time())}.mp4")
                        temp_mp4_path = os.path.join(DATA_DIR, "temp_final_video.mp4")

                        # --- SAFE STREAM FALLBACK ---
                        play_target_filename = ""
                        if not is_silent_playback:
                            ext = os.path.splitext(output_path)[1].lower() or ".mp3"
                            play_target_filename = f"play_{int(my_render_id)}{ext}"
                            play_target_path = os.path.join(DATA_DIR, play_target_filename)
                            try: shutil.copy2(output_path, play_target_path)
                            except: play_target_filename = os.path.basename(output_path)

                        b64_audio_data = None
                        if not is_silent_playback and not chk_safe_audio.value and audio_player:
                            try:
                                with open(output_path, "rb") as f:
                                    b64_audio_data = base64.b64encode(f.read()).decode('utf-8')
                            except Exception as e:
                                log_error(f"B64 encode err: {e}")

                        is_processing[0] = False

                        # ==================================================
                        # BUILD THE SYNC MAP *BEFORE* THE AUDIO STARTS
                        # (finds real speech start/end + real pauses)
                        # ==================================================
                        family = dd_font.value if dd_font.value != "Default" else None
                        try: current_f_size = int(dd_size.value)
                        except: current_f_size = 16

                        hl_on = bool(chk_highlight.value)
                        scroll_on = bool(chk_autoscroll.value)
                        need_sync = hl_on or scroll_on
                        timeline = analyze_audio_timeline(output_path if not is_silent_playback else "", content)
                        unit_meta, unit_ctrls, unit_paras, units_per_chunk = build_reading_units(content, current_f_size, family)
                        sync_map, word_sync = None, None
                        if need_sync and unit_meta:
                            eng_val = dd_sync_engine.value or "Auto"
                            wmodel = dd_whisper_model.value or "base"
                            if (not is_silent_playback) and not eng_val.startswith("Classic"):
                                def _wstatus(msg):
                                    ui_call(lambda: (set_loading(True, msg, is_rendering_audio=True), page.update()))
                                try:
                                    align_cache = os.path.join(cache_dir, f"{pure_text_hash}.align.json")
                                    wt = smart_word_times(output_path, content, eng_val, wmodel, align_cache, _wstatus, list(groq_backend.keys))
                                    if wt:
                                        word_sync = WordSync([m["wi"] for m in unit_meta], wt)
                                    else:
                                        ui_call(lambda: show_snack("Smart sync needs a Groq API key (🔑) or local Whisper. Using classic sync.", "orange"))
                                except Exception as wex:
                                    log_error(f"Smart sync error: {wex}\n{traceback.format_exc()}")
                                    ui_call(lambda: show_snack("Smart sync failed (see error_log.txt). Using classic sync.", "orange"))
                            if word_sync is None:
                                sync_map = SyncMap(unit_meta, timeline["duration"], timeline["speech_start"], timeline["speech_end"], timeline["gaps"])
                        if app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id:
                            return
                        reading_state["ctrls"] = unit_ctrls
                        rec_sync = {"audio_t0": None, "video_t0": None, "thread": None}

                        def ui_updates():
                            reading_body.controls = unit_paras
                            reading_column.controls = [reading_text, reading_body] + ([reset_holder["c"]] if reset_holder["c"] else [])
                            reading_text.size = current_f_size
                            reading_text.font_family = family

                            # --- AUDIO START ---
                            if not is_silent_playback:
                                if chk_safe_audio.value:
                                    if LOCAL_AUDIO_PORT:
                                        stream_url = f"http://127.0.0.1:{LOCAL_AUDIO_PORT}/{play_target_filename}"
                                        page.launch_url(stream_url)
                                    else:
                                        show_snack("Local server failed. Cannot play audio.", "red")

                                elif PYGAME_AVAILABLE and not is_android_sys():
                                    if not pygame.mixer.get_init(): pygame.mixer.init()
                                    pygame.mixer.music.load(output_path)
                                    pygame.mixer.music.play()

                                elif audio_player:
                                    try:
                                        audio_player.src = None
                                        audio_player.src_base64 = b64_audio_data
                                        page.update()
                                        audio_player.update()
                                        audio_player.play()
                                    except Exception as e:
                                        show_snack(f"Audio playback error: {e}", "red")
                                else:
                                    show_snack("Audio engine missing! Install pygame or check 'Bypass Red Screen' in Voice settings.", "red")
                            android_clock["got"] = False
                            android_clock["pos"] = 0.0
                            rec_sync["audio_t0"] = time.time()

                            if record_video and is_cached:
                                status_msg = "🔴 Recording Video (Audio from Cache)..."
                            elif record_video and is_silent_playback:
                                status_msg = "🔴 Recording Video (Silent Mode)..."
                            elif record_video:
                                status_msg = "🔴 Recording Video..."
                            elif is_cached:
                                status_msg = "🔊 Playing from Cache..."
                            elif is_silent_playback:
                                status_msg = "📜 Auto-Scrolling Silently..."
                            else:
                                status_msg = "🔊 Playing Audio..."

                            set_loading(False, status_msg)
                            tts_btn.text = "⏹️ Stop Audio"
                            tts_btn.style = ft.ButtonStyle(bgcolor="red700", color="white", shape=ft.RoundedRectangleBorder(radius=8))
                            tts_btn.disabled = False

                            top_play_btn.text = "⏹️"
                            top_play_btn.disabled = False

                            if record_video:
                                top_rec_btn.style = ft.ButtonStyle(color="red700", bgcolor="white")
                                top_rec_btn.text = "⏹️ Stop Rec"
                                reading_container.border = None

                            text_container_gen.content = reading_container

                            try:
                                tts_btn.update()
                                top_play_btn.update()
                                top_rec_btn.update()
                                text_container_gen.update()
                                page.update()
                            except: pass

                            if unit_ctrls and hl_on:
                                paint_unit(0, HILITE_COLOR)
                            safe_fire_scroll(offset=0.0)

                        ui_call(ui_updates)

                        # ==================================================
                        # SCREEN RECORDER (clock-locked: duplicates frames if
                        # the grab is slow, so video length == real time)
                        # ==================================================
                        if record_video and VIDEO_EXPORT_AVAILABLE:
                            is_video_recording[0] = True

                            def frame_grabber_task():
                                nonlocal temp_avi_path
                                try:
                                    with mss.mss() as sct:
                                        left, top, width, height = 0, 0, 0, 0
                                        scale = 1.0

                                        if platform.system().lower() == "windows":
                                            try:
                                                import ctypes
                                                from ctypes import wintypes
                                                ctypes.windll.user32.SetProcessDPIAware()
                                                hwnd = ctypes.windll.user32.FindWindowW(None, page.title)
                                                if hwnd:
                                                    rect = wintypes.RECT()
                                                    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
                                                    pt = wintypes.POINT(0, 0)
                                                    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))

                                                    dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
                                                    scale = dpi / 96.0

                                                    header_offset = int(60 * scale)

                                                    left = pt.x
                                                    top = pt.y + header_offset
                                                    width = rect.right - rect.left
                                                    height = (rect.bottom - rect.top) - header_offset
                                            except Exception as e:
                                                log_error(f"Windows API Rect Error: {e}")

                                        if width <= 0 or height <= 0:
                                            try:
                                                left, top = int(page.window.left), int(page.window.top)
                                                width, height = int(page.window.width), int(page.window.height)
                                                top += int(80 * scale)
                                                height -= int(100 * scale)
                                            except Exception:
                                                left, top, width, height = 0, 0, 450, 850

                                        width -= (width % 2)
                                        height -= (height % 2)

                                        monitor = {"top": int(top), "left": int(left), "width": int(width), "height": int(height)}

                                        fps = 20.0

                                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                                        out = cv2.VideoWriter(temp_avi_path, fourcc, fps, (monitor["width"], monitor["height"]))

                                        if not out.isOpened():
                                            fourcc = cv2.VideoWriter_fourcc(*"XVID")
                                            temp_fallback_path = temp_avi_path.replace(".mp4", ".avi")
                                            out = cv2.VideoWriter(temp_fallback_path, fourcc, fps, (monitor["width"], monitor["height"]))
                                            if out.isOpened():
                                                temp_avi_path = temp_fallback_path

                                        if not out.isOpened():
                                            raise Exception("cv2.VideoWriter failed to open. System might be missing codecs.")

                                        video_t0 = time.time()
                                        rec_sync["video_t0"] = video_t0
                                        written = 0

                                        while is_video_recording[0]:
                                            img = np.array(sct.grab(monitor))
                                            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                                            # How many frames SHOULD exist by now? Write that many.
                                            due = int((time.time() - video_t0) * fps) + 1
                                            to_write = max(1, min(due - written, 60))
                                            for _ in range(to_write):
                                                out.write(frame)
                                                written += 1

                                            wait = (video_t0 + written / fps) - time.time()
                                            if wait > 0:
                                                time.sleep(wait)
                                        out.release()
                                except Exception as e:
                                    log_error(f"Frame Grabber error: {e}")
                                    is_video_recording[0] = False
                                    def _er_snack():
                                        show_snack(f"Recorder Error: {str(e)}", "red")
                                        page.update()
                                    ui_call(_er_snack)

                            grab_thread = threading.Thread(target=frame_grabber_task, daemon=True)
                            rec_sync["thread"] = grab_thread
                            grab_thread.start()

                        is_audio_playing[0] = True

                        # ==================================================
                        # PLAYBACK MONITOR: locks highlight + scroll to the voice
                        # ==================================================
                        def monitor_playback():
                            try:
                                wait_until = time.time() + 5
                                while rec_sync["audio_t0"] is None and time.time() < wait_until:
                                    time.sleep(0.02)
                                audio_t0 = rec_sync["audio_t0"] or time.time()
                                audio_dur = timeline["duration"]

                                use_pg_clock = PYGAME_AVAILABLE and not is_android_sys() and not is_silent_playback and not chk_safe_audio.value
                                step_units = max(1, round(6.0 / units_per_chunk))   # re-anchor scroll every ~6 words
                                back_units = max(1, round(8.0 / units_per_chunk))   # keep ~8 words of context above
                                last_idx, last_target = 0, -1
                                painted = hl_on

                                while is_audio_playing[0]:
                                    if use_pg_clock:
                                        if not pygame.mixer.music.get_busy(): break
                                        pos = pygame.mixer.music.get_pos() / 1000.0   # real position of the audio itself
                                        if pos < 0: pos = time.time() - audio_t0
                                    else:
                                        pos = time.time() - audio_t0
                                        use_ev = (audio_player is not None and not is_silent_playback and not chk_safe_audio.value
                                                  and android_clock["got"] and (time.time() - android_clock["t"]) < 1.5)
                                        if use_ev:   # real position reported by the phone's player
                                            pos = android_clock["pos"] + (time.time() - android_clock["t"])
                                        if (is_silent_playback or chk_safe_audio.value) and pos >= audio_dur: break
                                        if not android_clock["got"] and pos >= audio_dur + 3: break
                                        if audio_player is not None and android_clock["got"] and (time.time() - android_clock["t"]) > 3.0: break
                                        if pos > 7200: break

                                    try: offset = (float(scroll_speed_slider.value) - 20.0) * 0.1
                                    except Exception: offset = 0.0

                                    if (word_sync is not None or sync_map is not None) and unit_ctrls:
                                        t_q = pos + SYNC_LOOKAHEAD + offset
                                        idx = word_sync.unit_at(t_q) if word_sync is not None else sync_map.unit_at(t_q)
                                        hl_now = bool(chk_highlight.value)   # live toggle
                                        if idx != last_idx or hl_now != painted:
                                            if last_idx >= 0 and painted: paint_unit(last_idx, "white")
                                            if hl_now: paint_unit(idx, HILITE_COLOR)
                                            painted = hl_now
                                            last_idx = idx
                                            if chk_autoscroll.value:
                                                target = max(0, (idx // step_units) * step_units - back_units)
                                                if target != last_target:
                                                    last_target = target
                                                    safe_fire_scroll(key=f"u{target}")

                                    time.sleep(0.08)

                                is_audio_playing[0] = False
                                is_video_recording[0] = False

                                gt = rec_sync.get("thread")
                                if gt is not None:
                                    try: gt.join(timeout=5)
                                    except: pass
                                time.sleep(0.3)

                                def reset_ui():
                                    tts_btn.text = "🔊 Read Aloud"
                                    tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color="white", shape=ft.RoundedRectangleBorder(radius=8))
                                    top_play_btn.text = "▶️"
                                    top_rec_btn.style = ft.ButtonStyle(color="red400", bgcolor="transparent")
                                    top_rec_btn.text = "⏺️ Rec"

                                    if current_fullscreen_mode[0] == "none":
                                        reading_container.border = make_border(1.5, "blue600")

                                    text_container_gen.content = text_area
                                    try:
                                        tts_btn.update()
                                        top_play_btn.update()
                                        top_rec_btn.update()
                                        text_container_gen.update()
                                        refresh_fav_list()
                                        page.update()
                                    except: pass

                                ui_call(reset_ui)

                                if record_video and VIDEO_EXPORT_AVAILABLE and os.path.exists(temp_avi_path):
                                    def _show_mux():
                                        set_loading(True, "⏳ Compiling final MP4 Video... Please wait.")
                                        page.update()
                                    ui_call(_show_mux)

                                    def mux_video():
                                        try:
                                            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

                                            cmd = [ffmpeg_exe, "-y", "-i", temp_avi_path]

                                            if output_path and os.path.exists(output_path):
                                                # The audio started BEFORE the first video frame was captured.
                                                # Trim that head start so voice and picture line up exactly.
                                                a0, v0 = rec_sync.get("audio_t0"), rec_sync.get("video_t0")
                                                head_start = (v0 - a0) if (a0 and v0) else 0.0
                                                if head_start >= 0:
                                                    cmd += ["-ss", f"{head_start:.3f}", "-i", output_path]
                                                else:
                                                    cmd += ["-itsoffset", f"{-head_start:.3f}", "-i", output_path]
                                                cmd += ["-map", "0:v:0", "-map", "1:a:0",
                                                        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                                                        "-c:a", "aac", "-shortest"]
                                            else:
                                                cmd += ["-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p"]

                                            cmd.append(temp_mp4_path)

                                            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=_hidden_startupinfo())

                                            if process.returncode != 0:
                                                err_msg = process.stderr.decode('utf-8', errors='ignore')
                                                raise Exception(f"FFmpeg Compilation Error:\n{err_msg}")

                                            import tkinter as tk
                                            from tkinter import filedialog
                                            root = tk.Tk()
                                            root.withdraw()
                                            root.attributes('-topmost', True)
                                            save_path = filedialog.asksaveasfilename(
                                                parent=root,
                                                title="Save Devotional Video",
                                                initialfile=f"Devotional_{int(time.time())}.mp4",
                                                defaultextension=".mp4",
                                                filetypes=[("MP4 Video", "*.mp4")]
                                            )
                                            root.destroy()

                                            if save_path:
                                                shutil.move(temp_mp4_path, save_path)
                                                def _sc():
                                                    show_snack(f"✅ Video saved to {save_path}", "green")
                                                    page.update()
                                                ui_call(_sc)
                                            else:
                                                def _cn():
                                                    show_snack("Video save cancelled.", "orange")
                                                    page.update()
                                                ui_call(_cn)

                                        except Exception as ex:
                                            def _er():
                                                show_error_dialog(f"Video Compilation Error:\n{ex}")
                                                page.update()
                                            ui_call(_er)
                                        finally:
                                            def _dn():
                                                set_loading(False)
                                                page.update()
                                            ui_call(_dn)
                                            try:
                                                if os.path.exists(temp_avi_path): os.remove(temp_avi_path)
                                                if os.path.exists(temp_mp4_path): os.remove(temp_mp4_path)
                                            except: pass

                                    threading.Thread(target=mux_video, daemon=True).start()

                            except Exception as mon_ex:
                                log_error(f"Playback monitor error: {mon_ex}\n{traceback.format_exc()}")
                                is_audio_playing[0] = False

                        threading.Thread(target=monitor_playback, daemon=True).start()

                    except Exception as ex:
                        log_error(f"Playback Error: {ex}\n{traceback.format_exc()}")
                        def _plerr():
                            show_error_dialog(f"Playback Error: {ex}")
                            show_snack("Failed to play audio.", "red")
                            page.update()
                        ui_call(_plerr)
                else:
                    def _gerr():
                        if app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id:
                            return

                        show_error_dialog(result)
                        show_snack("Failed to generate audio.", "red")
                        page.update()
                    ui_call(_gerr)
            finally:
                if app_state.get("current_render_id") == my_render_id:
                    app_state["is_rendering_audio"] = False
                    if not is_audio_playing[0] and not is_video_recording[0]:
                        def _rls():
                            set_loading(False)
                            page.update()
                        ui_call(_rls)

        threading.Thread(target=worker, daemon=True).start()

    pending_link = {"content": ""}

    def _finish_link(selected_file, content):
        try:
            pure_text_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            cache_dir = getattr(tf_cache_dir, 'value', "").strip() or DATA_DIR
            os.makedirs(cache_dir, exist_ok=True)

            ui_call(lambda: (set_loading(True, "Preparing audio..."), page.update()))
            convert_to_playable(selected_file, cache_dir, pure_text_hash)

            def _sc():
                set_loading(False)
                refresh_fav_list()
                show_snack("✅ Audio linked! You can now hit Play without rendering.", "green")
                page.update()
            ui_call(_sc)
        except Exception as ex:
            def _er():
                set_loading(False)
                show_snack(f"Error linking audio: {ex}", "red")
                page.update()
            ui_call(_er)

    def on_picker_result(e):
        try:
            if e.files and e.files[0].path:
                threading.Thread(target=_finish_link, args=(e.files[0].path, pending_link["content"]), daemon=True).start()
            elif e.files:
                show_snack("Could not read the selected file.", "red")
        except Exception as ex:
            show_snack(f"File picker error: {ex}", "red")

    file_picker = None
    if is_android_sys():
        try:
            file_picker = ft.FilePicker(on_result=on_picker_result)
            page.overlay.append(file_picker)
        except Exception as ex:
            log_error(f"FilePicker init failed: {ex}")

    def on_link_audio(e):
        content = text_area.value.strip()
        if not content or content.startswith("Welcome!"):
            show_snack("Please generate or paste text first to link audio to it.", "orange")
            return

        if is_android_sys():
            if file_picker is None:
                show_snack("File picker is not available on this device.", "red")
                return
            pending_link["content"] = content
            try:
                file_picker.pick_files(dialog_title="Select audio file (.weba, .mp3, .m4a, .ogg...)",
                                       file_type=ft.FilePickerFileType.ANY, allow_multiple=False)
            except Exception as ex:
                show_snack(f"Could not open file picker: {ex}", "red")
            return

        def _open_picker():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
                selected_file = filedialog.askopenfilename(
                    parent=root, title="Select Audio File",
                    filetypes=[("Any audio / video", "*.weba *.webm *.mp3 *.wav *.ogg *.oga *.opus *.m4a *.aac *.flac *.wma *.aiff *.aif *.amr *.mp4 *.mkv *.mov"),
                               ("All files", "*.*")])
                root.destroy()
                if selected_file:
                    _finish_link(selected_file, content)
            except Exception as ex:
                def _er():
                    set_loading(False)
                    show_snack(f"Error linking audio: {ex}", "red")
                    page.update()
                ui_call(_er)

        threading.Thread(target=_open_picker, daemon=True).start()

    def copy_to_clipboard(e):
        try:
            if hasattr(page, 'set_clipboard'):
                page.set_clipboard(text_area.value)
            else:
                import pyperclip
                pyperclip.copy(text_area.value)
            show_snack("Copied to clipboard!", "green")
        except Exception:
            show_snack("Auto-copy unavailable. Please long-press text to copy.", "orange")

    def on_record_clicked(e):
        if is_android_sys():
            show_snack("Screen recording via Python is only supported on PC. On Mobile, please use your phone's native screen recorder.", "orange")
            return
        if not VIDEO_EXPORT_AVAILABLE:
            show_error_dialog("Missing Video Libraries!\n\nThe auto-installer could not set up the recording libraries. Delete the .venv_* folder next to the app and run it again (internet required).")
            return

        if is_audio_playing[0]:
            on_play_tts(e)
        else:
            on_play_tts(e, record_video=True)

    def refresh_fav_list():
        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if not cache_dir: cache_dir = DATA_DIR

        fav_list.controls.clear()
        for i, fav in enumerate(reversed(favorites)):
            real_idx = len(favorites) - 1 - i
            is_selected = selected_fav_idx[0] == real_idx

            def make_click(idx): return lambda e: select_fav(idx)
            def make_edit(idx): return lambda e: edit_specific_fav(idx)
            def make_delete(idx): return lambda e: delete_specific_fav(idx)

            pure_hash = hashlib.md5(fav.get("content", "").encode('utf-8')).hexdigest()
            has_cache = bool(find_cached_audio(cache_dir, pure_hash))
            cache_icon = " 🎵" if has_cache else ""

            action_row = ft.Row([
                ft.TextButton("✏️", on_click=make_edit(real_idx), width=40, style=ft.ButtonStyle(padding=0)),
                ft.TextButton("🗑️", on_click=make_delete(real_idx), width=40, style=ft.ButtonStyle(padding=0, color="red400"))
            ], spacing=0)

            content_row = ft.Row([
                ft.Text(fav.get("title", "Saved Document") + cache_icon, weight=ft.FontWeight.BOLD, color="white" if is_selected else "white70", expand=True),
                action_row
            ])

            fav_list.controls.append(
                ft.Container(
                    content=content_row,
                    bgcolor="blue700" if is_selected else "transparent",
                    padding=10, border_radius=5, on_click=make_click(real_idx)
                )
            )
        page.update()

    def select_fav(idx):
        selected_fav_idx[0] = idx
        fav_text_area.value = favorites[idx].get("content", "")
        refresh_fav_list()

    def edit_specific_fav(idx):
        selected_fav_idx[0] = idx
        fav = favorites[idx]
        text_area.value = fav.get("content", "")
        reading_text.value = text_area.value
        switch_to_tab("gen")
        show_snack("Loaded favorite into generator.", "green")

    def delete_specific_fav(idx):
        try:
            content_to_delete = favorites[idx].get("content", "")
            cache_dir = getattr(tf_cache_dir, 'value', "").strip()
            if not cache_dir: cache_dir = DATA_DIR
            pure_hash = hashlib.md5(content_to_delete.encode('utf-8')).hexdigest()
            remove_cached_audio(cache_dir, pure_hash)
        except: pass

        del favorites[idx]
        if selected_fav_idx[0] == idx:
            selected_fav_idx[0] = None
            fav_text_area.value = "Select a favorite document to read here..."
        elif selected_fav_idx[0] is not None and selected_fav_idx[0] > idx:
            selected_fav_idx[0] -= 1

        save_favorites()
        refresh_fav_list()
        show_snack("Favorite deleted.", "green")
        page.update()

    def on_save_favorite(e):
        content = text_area.value.strip()
        if not content or content.startswith("Welcome!"): return show_snack("Please generate or write a document first.", "orange")
        title = extract_title(content)
        for fav in favorites:
            if fav["content"] == content: return show_snack("This exact document is already in your favorites!", "orange")
        favorites.append({"title": title, "content": content})
        save_favorites()
        refresh_fav_list()

        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if not cache_dir: cache_dir = DATA_DIR
        os.makedirs(cache_dir, exist_ok=True)

        audio_path = app_state.get("last_audio_path")
        pure_text_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

        cached_status = "❤️ Document saved to favorites!"
        if audio_path and os.path.exists(audio_path):
            ext = os.path.splitext(audio_path)[1].lower() or ".mp3"
            cache_path_pure = os.path.join(cache_dir, f"{pure_text_hash}{ext}")
            if not find_cached_audio(cache_dir, pure_text_hash):
                try:
                    shutil.copy2(audio_path, cache_path_pure)
                    cached_status = "❤️ Document & Audio cached for offline playback!"
                except Exception as ex:
                    print(f"Audio cache error: {ex}")

        show_snack(cached_status, "green")

    def open_keys_dialog(e):
        backend_name = dd_backend.value
        if backend_name == "LM Studio (Local)": return show_snack("LM Studio runs locally and does not require API keys.", "blue400")

        backend_instance = get_active_backend()
        keys_list = ft.ListView(spacing=5, height=150)

        def refresh_keys_list():
            keys_list.controls.clear()
            for k in backend_instance.keys: keys_list.controls.append(ft.Text(f"{k[:8]}...{k[-4:]}" if len(k) > 12 else k))
            page.update()

        new_key_field = ft.TextField(label=f"New {backend_name} API Key")

        def add_key_action(e):
            val = new_key_field.value or ""
            k = val.strip()
            if k and k not in backend_instance.keys:
                backend_instance.keys.append(k)
                backend_instance.save_keys(backend_instance.keys)
                new_key_field.value = ""
                refresh_keys_list()
                show_snack("Key added!", "green")

        def remove_keys_action(e):
            if backend_instance.keys:
                backend_instance.keys.pop()
                backend_instance.save_keys(backend_instance.keys)
                refresh_keys_list()
                show_snack("Last key removed!", "orange")

        dlg = ft.AlertDialog(
            title=ft.Text(f"Manage {backend_name} API Keys"),
            content=ft.Column([
                ft.Text("The app will automatically rotate through these keys.", italic=True, size=12),
                keys_list, new_key_field,
                ft.Row([ft.TextButton("Add", on_click=add_key_action, style=ft.ButtonStyle(bgcolor="green", color="white")), ft.TextButton("Remove Last", on_click=remove_keys_action, style=ft.ButtonStyle(bgcolor="red", color="white"))])
            ], tight=True),
            actions=[ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        )
        refresh_keys_list()
        show_dialog(dlg)

    # --- WIRE UP ALL BUTTON CALLBACKS ---
    text_area.on_change = on_text_changed
    top_play_btn.on_click = on_play_tts
    top_rec_btn.on_click = on_record_clicked
    copy_btn.on_click = copy_to_clipboard
    generate_btn.on_click = on_generate
    prompt_gen_btn.on_click = open_generate_ai_dialog
    revise_btn.on_click = on_revise_standard
    prompt_rev_btn.on_click = open_revise_ai_dialog
    translate_btn.on_click = on_apply_verse
    qa_btn.on_click = on_generate_qa
    tts_btn.on_click = on_play_tts
    save_btn.on_click = on_save_favorite
    backup_btn.on_click = perform_backup
    restore_btn.on_click = perform_restore
    link_audio_btn.on_click = on_link_audio
    el_manage_btn.on_click = open_el_dialog
    fish_manage_btn.on_click = open_fish_dialog
    test_vb_btn.on_click = test_voicebox_conn
    btn_browse_cache.on_click = browse_cache_dir
    btn_clear_cache.on_click = clear_cache_dir

    # =======================================================
    # UI TABS CONSTRUCTION
    # =======================================================
    text_container_gen = ft.Container(content=text_area, width=float('inf'), expand=8)

    gen_actions_container = ft.Column([
        ft.Row([generate_btn], expand=2, vertical_alignment="stretch"),
        ft.Row([prompt_gen_btn, revise_btn], expand=1, vertical_alignment="stretch", spacing=5),
        ft.Row([prompt_rev_btn, translate_btn], expand=1, vertical_alignment="stretch", spacing=5),
        ft.Row([qa_btn, tts_btn], expand=1, vertical_alignment="stretch", spacing=5),
        ft.Row([save_btn, link_audio_btn], expand=1, vertical_alignment="stretch", spacing=5)
    ], expand=6, spacing=5)

    settings_tab_content = ft.Column([
        ft.Text("Content & Display Setup", weight=ft.FontWeight.BOLD, size=18, color="blue400"),
        ft.ResponsiveRow([
            ft.Column([dd_format], col={"sm": 6, "xs": 6}), ft.Column([dd_style], col={"sm": 6, "xs": 6}),
            ft.Column([dd_version], col={"sm": 6, "xs": 6}), ft.Column([dd_theme], col={"sm": 6, "xs": 6}),
            ft.Column([dd_length], col={"sm": 6, "xs": 6}), ft.Column([dd_lang], col={"sm": 6, "xs": 6}),
            ft.Column([dd_duration], col={"sm": 6, "xs": 6}), ft.Column([dd_font], col={"sm": 6, "xs": 6}),
            ft.Column([dd_size], col={"sm": 6, "xs": 6}),
        ]),
        ft.Divider(),
        ft.Text("AI Backend Models", weight=ft.FontWeight.BOLD, size=18, color="blue400"),
        ft.ResponsiveRow([
            ft.Column([dd_backend], col={"sm": 6, "xs": 6}), ft.Column([dd_model], col={"sm": 6, "xs": 6}),
        ]),
        ft.ResponsiveRow([ft.Column([tf_custom_model], col={"sm": 12, "xs": 12})]),
        ft.ResponsiveRow([ft.Column([tf_9router_url], col={"sm": 12, "xs": 12})]),
        ft.ResponsiveRow([ft.Column([btn_heal_models], col={"sm": 12, "xs": 12}), ft.Column([chk_autoheal], col={"sm": 12, "xs": 12})]),
        ft.Text("'Test & Fix Models' sends one tiny request per model (up to ~48 for 9Router) and lists ONLY the ones that answer right now. Claude API is pay-as-you-go; for FREE Claude connect Kiro AI in 9Router.", size=11, color="grey400"),
        ft.Divider(),
        ft.Text("Data Management", weight=ft.FontWeight.BOLD, size=18, color="blue400"),
        ft.ResponsiveRow([
            ft.Column([backup_btn], col={"xs": 6}), ft.Column([restore_btn], col={"xs": 6})
        ]),
        ft.Container(height=50)
    ], scroll="auto", expand=True)

    voice_tab_content = ft.Column([
        ft.Text("TTS Engine Setup", weight=ft.FontWeight.BOLD, size=18, color="purple400"),
        ft.ResponsiveRow([
            ft.Column([dd_tts_engine], col={"sm": 12, "xs": 12}),
            ft.Column([chk_autoplay], col={"sm": 6, "xs": 6}), ft.Column([chk_force_cache], col={"sm": 6, "xs": 6}),
            ft.Column([chk_safe_audio], col={"sm": 12, "xs": 12}),
            ft.Column([chk_highlight], col={"sm": 6, "xs": 6}), ft.Column([chk_autoscroll], col={"sm": 6, "xs": 6}),
            ft.Column([dd_sync_engine], col={"sm": 6, "xs": 6}), ft.Column([dd_whisper_model], col={"sm": 6, "xs": 6}),
            ft.Column([
                ft.Row([
                    ft.Text("Text Sync Fine-Tune (+ = text earlier, - = later):", font_family="Helvetica", size=13, weight="bold", color="grey400"),
                    slider_label
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                scroll_speed_slider
            ], col={"sm": 12, "xs": 12}),
        ]),
        ft.Divider(),
        ft.Text("TikTok Configuration", weight=ft.FontWeight.BOLD, size=16, color="pink400"),
        ft.ResponsiveRow([
            ft.Column([tf_tiktok_session], col={"sm": 6, "xs": 6}), ft.Column([dd_tiktok_voice], col={"sm": 6, "xs": 6}),
        ]),
        ft.Divider(),
        ft.Text("Edge TTS (Free, no key, PC only)", weight=ft.FontWeight.BOLD, size=16, color="cyan400"),
        ft.ResponsiveRow([ft.Column([dd_edge_voice], col={"sm": 12, "xs": 12})]),
        ft.Divider(),
        ft.Text("Voicebox Configuration", weight=ft.FontWeight.BOLD, size=16, color="green400"),
        ft.ResponsiveRow([
            ft.Column([tf_voicebox_url], col={"sm": 6, "xs": 12}),
            ft.Column([tf_voicebox_preset], col={"sm": 6, "xs": 6}),
            ft.Column([dd_voicebox_engine], col={"sm": 6, "xs": 6}),
            ft.Column([test_vb_btn], col={"sm": 12, "xs": 12}),
        ]),
        ft.Divider(),
        ft.Text("ElevenLabs & Fish Speech", weight=ft.FontWeight.BOLD, size=16, color="orange400"),
        ft.ResponsiveRow([
            ft.Column([dd_elevenlabs_preset], col={"sm": 6, "xs": 6}), ft.Column([el_manage_btn], col={"sm": 6, "xs": 6}),
            ft.Column([tf_fish_url], col={"sm": 12, "xs": 12}),
            ft.Column([dd_fish_preset], col={"sm": 6, "xs": 6}), ft.Column([fish_manage_btn], col={"sm": 6, "xs": 6}),
        ]),
        ft.Divider(),
        ft.Text("Offline Audio Cache", weight=ft.FontWeight.BOLD, size=16, color="cyan400"),
        ft.ResponsiveRow([
            ft.Column([ft.Row([tf_cache_dir, btn_browse_cache, btn_clear_cache], expand=True)], col={"sm": 12, "xs": 12}),
        ]),
        ft.Container(height=50)
    ], scroll="auto", expand=True)

    custom_border = make_border(1, "#374151")

    def open_cache_folder_cmd(e):
        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if not cache_dir: cache_dir = DATA_DIR
        os.makedirs(cache_dir, exist_ok=True)
        try:
            if platform.system() == "Windows":
                os.startfile(cache_dir)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", cache_dir])
            else:
                subprocess.Popen(["xdg-open", cache_dir])
        except Exception as ex:
            show_snack(f"Could not open folder: {ex}", "red")

    fav_title_row = ft.Row([
        ft.Text("Saved Documents", weight=ft.FontWeight.BOLD),
        ft.Container(expand=True),
        ft.TextButton("📁 Open Cache Folder", on_click=open_cache_folder_cmd, height=30, style=ft.ButtonStyle(padding=0))
    ])

    favorites_tab_content = ft.Column([
        fav_title_row,
        ft.Container(content=fav_list, expand=True, border=custom_border, border_radius=5, padding=5)
    ], expand=True)

    # =======================================================
    # FULLSCREEN & TAB NAVIGATION LOGIC
    # =======================================================
    def _hl_style():
        return ft.ButtonStyle(color="#FACC15" if chk_highlight.value else "grey600")

    hl_toggle_btn = ft.TextButton("🖍️", tooltip="Word highlight ON / OFF", style=_hl_style())

    def on_hl_changed(e=None):
        hl_toggle_btn.style = _hl_style()
        save_app_settings()
        try:
            hl_toggle_btn.update()
            chk_highlight.update()
        except Exception: pass

    def on_hl_toggle_click(e):
        chk_highlight.value = not chk_highlight.value
        on_hl_changed()
        show_snack("🖍️ Highlight ON" if chk_highlight.value else "Highlight OFF", "green" if chk_highlight.value else "orange")

    hl_toggle_btn.on_click = on_hl_toggle_click
    chk_highlight.on_change = on_hl_changed

    header_gen_left = ft.Row([
        ft.Text("Preview", weight="bold", color="grey500"),
        top_reset_voice_btn, top_play_btn, top_rec_btn, hl_toggle_btn, copy_btn
    ], alignment=ft.MainAxisAlignment.START, spacing=0)

    fs_portrait_btn = ft.TextButton("📱 Port", tooltip="Portrait Mode", on_click=lambda e: set_fullscreen("portrait"), style=ft.ButtonStyle(color="#60A5FA"))
    fs_landscape_btn = ft.TextButton("📺 Land", tooltip="Landscape Mode", on_click=lambda e: set_fullscreen("landscape"), style=ft.ButtonStyle(color="#60A5FA"))
    fs_exit_btn = ft.TextButton("↙️ Exit", tooltip="Exit Fullscreen", on_click=lambda e: set_fullscreen("none"), style=ft.ButtonStyle(color="#60A5FA"), visible=False)

    fs_portrait_btn.visible = True
    fs_landscape_btn.visible = True
    fs_exit_btn.visible = False

    fs_row = ft.Row([fs_portrait_btn, fs_landscape_btn, fs_exit_btn], spacing=0)
    if is_android_sys():
        top_rec_btn.visible = False   # screen recording is PC-only
        header_gen = ft.Row([header_gen_left, fs_row], scroll="auto", spacing=0)
    else:
        header_gen = ft.Row([header_gen_left, fs_row], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    generator_tab_content = ft.Column([header_gen, text_container_gen, ft.Divider(color="transparent", height=5), gen_actions_container], expand=True, spacing=0)

    tab_view_container = ft.Container(
        content=ft.Column([
            generator_tab_content,
            settings_tab_content,
            voice_tab_content,
            favorites_tab_content
        ], expand=True),
        expand=True,
        padding=10
    )

    active_tab_style = ft.ButtonStyle(bgcolor="#1D4ED8", color="white", shape=ft.RoundedRectangleBorder(radius=5), padding=make_padding(left=8, right=8, top=0, bottom=0))
    inactive_tab_style = ft.ButtonStyle(bgcolor="transparent", color="grey400", shape=ft.RoundedRectangleBorder(radius=5), padding=make_padding(left=8, right=8, top=0, bottom=0))

    gen_tab_btn = ft.TextButton("✨ Gen", expand=True, on_click=lambda e: switch_to_tab("gen"), style=inactive_tab_style)
    set_tab_btn = ft.TextButton("⚙️ Setup", expand=True, on_click=lambda e: switch_to_tab("set"), style=inactive_tab_style)
    voice_tab_btn = ft.TextButton("🗣️ Voice", expand=True, on_click=lambda e: switch_to_tab("voice"), style=inactive_tab_style)
    fav_tab_btn = ft.TextButton("❤️ Favs", expand=True, on_click=lambda e: switch_to_tab("fav"), style=inactive_tab_style)

    tabs_row_container = ft.Container(content=ft.Row([gen_tab_btn, set_tab_btn, voice_tab_btn, fav_tab_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=2), padding=make_padding(left=5, right=5, top=5))

    def switch_to_tab(tab_name):
        gen_tab_btn.style = inactive_tab_style
        set_tab_btn.style = inactive_tab_style
        voice_tab_btn.style = inactive_tab_style
        fav_tab_btn.style = inactive_tab_style

        generator_tab_content.visible = False
        settings_tab_content.visible = False
        voice_tab_content.visible = False
        favorites_tab_content.visible = False

        if tab_name == "gen":
            generator_tab_content.visible = True
            gen_tab_btn.style = active_tab_style
        elif tab_name == "set":
            settings_tab_content.visible = True
            set_tab_btn.style = active_tab_style
        elif tab_name == "voice":
            voice_tab_content.visible = True
            voice_tab_btn.style = active_tab_style
        else:
            favorites_tab_content.visible = True
            fav_tab_btn.style = active_tab_style

        page.update()

    def set_fullscreen(mode):
        current_fullscreen_mode[0] = mode
        if mode == "none":
            is_fullscreen[0] = False
            if not is_android_sys():
                set_window_size(page, 450, 850)

            if not is_video_recording[0]:
                reading_container.border = make_border(1.5, "blue600")

            reading_container.padding = make_padding(left=20, right=20, top=15, bottom=15)
        elif mode == "portrait":
            is_fullscreen[0] = True
            if not is_android_sys():
                set_window_size(page, 450, 800)
            reading_container.border = None
            reading_container.padding = make_padding(left=25, right=25, top=35, bottom=35)
        elif mode == "landscape":
            is_fullscreen[0] = True
            if not is_android_sys():
                set_window_size(page, 800, 450)
            reading_container.border = None
            reading_container.padding = make_padding(left=40, right=40, top=35, bottom=35)

        title_row.visible = not is_fullscreen[0]
        status_row.visible = not is_fullscreen[0]
        tabs_row_container.visible = not is_fullscreen[0]
        gen_actions_container.visible = not is_fullscreen[0]

        if is_fullscreen[0]:
            tab_view_container.padding = 0
            fs_portrait_btn.visible = False
            fs_landscape_btn.visible = False
            fs_exit_btn.visible = True
        else:
            tab_view_container.padding = 10
            fs_portrait_btn.visible = True
            fs_landscape_btn.visible = True
            fs_exit_btn.visible = False

        page.update()

    title_row = ft.Row(
        [ft.Container(width=45), ft.Text("Edu's Daily Devotional", size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER), ft.TextButton("🔑", on_click=open_keys_dialog, width=45, height=45, tooltip="API Keys", style=ft.ButtonStyle(padding=0))],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
    )

    status_row = ft.Row([pr, status_text], alignment=ft.MainAxisAlignment.CENTER)
    page.add(title_row, status_row, tabs_row_container, tab_view_container)

    switch_to_tab("gen")
    refresh_fav_list()
    update_font()
    apply_backend_models(True)

    # =======================================================
    # NATIVE WINDOW EVENT HANDLER & ZOMBIE KILLER
    # =======================================================
    def handle_window_event(e):
        if e.data == "close":
            save_app_settings()
            os._exit(0)
        elif e.data in ["maximize", "unmaximize", "restore"]:
            is_max = (e.data == "maximize")
            if is_max:
                reading_container.border = None
                reading_container.padding = make_padding(left=30, right=30, top=20, bottom=20)
                text_container_gen.height = None
                text_container_gen.expand = True
            else:
                reading_container.border = make_border(1.5, "blue600")
                reading_container.padding = make_padding(left=20, right=20, top=15, bottom=15)
                text_container_gen.height = 380
                text_container_gen.expand = False
                if not is_android_sys():
                    try:
                        page.window.width = 450
                        page.window.height = 850
                    except: pass
            page.update()

    try:
        page.window.prevent_close = False
        page.window.on_event = handle_window_event
    except AttributeError:
        try:
            page.window_prevent_close = False
            page.on_window_event = handle_window_event
        except Exception: pass

    def force_clean_exit(e=None):
        save_app_settings()

    page.on_disconnect = force_clean_exit


if __name__ == "__main__":
    try:
        if hasattr(ft, "app"):
            ft.app(target=main)
        else:
            ft.run(main)
    except Exception as e:
        _set_console_visible(True)   # bring the console back so you can SEE the error
        print("\n❌ FATAL CRASH OCCURRED ❌")
        traceback.print_exc()
        log_error(f"Startup crash:\n{traceback.format_exc()}")
        if not is_android_sys(): input("\nPress Enter to close this window...")

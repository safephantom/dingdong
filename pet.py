"""딩동 펫 - 정해진 간격(정각 기준)마다 튀어나와 시간을 읽어주고 응원해주는 데스크톱 펫 (Windows).

음성: Google Cloud TTS(Chirp3 HD) 중심. 한 번 만든 mp3는 audio_cache/ 에 저장해 재사용하고,
API 사용은 사용 시간대·월 글자 수 한도로 제한한다. 실패하면 edge-tts로 대체하고, 그것도 안 되면 말풍선만 띄운다.

소리를 낼 수 없는 자리에서는 '무음 모드'로 딩동·음성을 끄고, 화면 테두리 번쩍임·반짝이·폴짝 뛰기 같은
시각 효과만으로 알린다. 원하면 직접 고른 GIF를 펫 뒤에서 함께 재생할 수도 있다.
"""
import asyncio
import base64
import ctypes
import hashlib
import json
import math
import os
import random
import sys
import threading
import time
import tkinter as tk
import urllib.request
from ctypes import wintypes
from tkinter import filedialog, messagebox, ttk

try:
    import winsound
except ImportError:
    sys.exit("Windows 전용 앱입니다.")

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
KEY_FILE = os.path.join(HERE, "tts_api_key.txt")
CACHE_DIR = os.path.join(HERE, "audio_cache")
USAGE_FILE = os.path.join(HERE, "usage.json")

W, H = 300, 320
PET_TOP = 190          # 캔버스 안에서 펫 머리 꼭대기 y
PEEK = 55              # 숨어 있을 때 화면에 보이는 높이(px)
KEY = "#010101"        # 투명 처리할 색

# 시각 효과: 화면 테두리 글로우(바깥부터 inset, 굵기, 색), 반짝이 색
GLOW_BANDS = [(0, 4, "#fff8d6"), (4, 6, "#ffd54f"), (10, 8, "#ffb300"), (18, 10, "#fb8c00")]
SPARK_COLORS = ("#ffd54f", "#fff59d", "#ffffff", "#ffb74d", "#b3e5fc", "#f8bbd0")
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x08000000

# 잊으면 안 되는 일: 정해진 요일·시각에 다른 설정을 모두 제치고 화려하게 알린다.
SPECIAL_WEEKDAY = 0                 # 0=월요일 ... 6=일요일
SPECIAL_AT = "10:55"
SPECIAL_TEXT = "무료음료창고 개방해 주세요 !!!"
SPECIAL_HOLD = 15                   # 화면에 붙잡아 두는 시간(초). 펫을 누르면 바로 닫힌다
SPECIAL_CATCHUP = 5                 # 절전 등으로 놓쳤어도 이 시간(분) 안에는 늦게라도 알린다
PARTY_COLORS = ("#ff4081", "#ffd54f", "#40c4ff", "#69f0ae", "#b388ff", "#ff6e40")
PARTY_INK = ("#b71c1c", "#1a237e", "#1b5e20")   # 글자는 읽혀야 하니 진한 색으로만 번갈아

# 여성 음성만. Chirp3 HD(최신 고품질) → Neural2 → WaveNet → Standard 순으로 자연스럽다.
_HD = [("아오이데", "Aoede"), ("코레", "Kore"), ("레다", "Leda"), ("제피르", "Zephyr"), ("아케르나르", "Achernar"),
       ("아우토노에", "Autonoe"), ("칼리로에", "Callirrhoe"), ("데스피나", "Despina"), ("에리노메", "Erinome"),
       ("가크룩스", "Gacrux"), ("라오메데이아", "Laomedeia"), ("풀케리마", "Pulcherrima"), ("술라파트", "Sulafat"),
       ("빈데미아트릭스", "Vindemiatrix")]
VOICES = {f"[HD] {ko}": f"google:ko-KR-Chirp3-HD-{en}" for ko, en in _HD}
VOICES.update({
    "[Neural2] A": "google:ko-KR-Neural2-A",
    "[Neural2] B": "google:ko-KR-Neural2-B",
    "[WaveNet] A": "google:ko-KR-Wavenet-A",
    "[WaveNet] B": "google:ko-KR-Wavenet-B",
    "[Standard] A (기본 품질)": "google:ko-KR-Standard-A",
    "[Standard] B (기본 품질)": "google:ko-KR-Standard-B",
    "[무료] 선희 (edge-tts)": "edge:ko-KR-SunHiNeural",
})
EDGE_FALLBACK = "edge:ko-KR-SunHiNeural"
PREVIEW_TEXT = "안녕하세요! 지금은 오후 3시 20분이에요. 오늘도 힘내봐요!"

DEFAULTS = {
    "interval_min": 10, "speak": True, "voice": "google:ko-KR-Chirp3-HD-Aoede",
    "sound": "", "messages": [],
    "api_from": "07:40", "api_to": "12:00",   # 이 시간대에만 새 '시각 멘트'를 API로 생성
    "monthly_char_limit": 50000,              # 한 달 API 글자 수 상한
    "silent": True,           # 무음 모드(기본값): 딩동·음성 없이 화면 효과로만 알린다
    "quiet_sec": 8,           # 소리 없이 알릴 때 말풍선을 띄워두는 시간(초)
    "fx_glow": True,          # 화면 테두리 번쩍이기
    "fx_sparkle": True,       # 펫 주변 반짝이
    "fx_hop": True,           # 말하는 동안 폴짝폴짝 뛰기
    "fx_gif": "",             # 펫 뒤에서 재생할 효과 GIF(선택)
    "pos": None,              # 끌어다 놓은 자리 [x, 그 모니터 작업 영역의 아래쪽 y]
    "special": True,          # 월요일 특별 알림 사용
}

# 시각 읽기 문구. {t} 는 '오후 7시 10분' / '오후 7시 정각' (항상 받침으로 끝나 '이' 계열이 자연스럽다)
TIME_TEMPLATES = [
    "지금 시각은 {t}입니다.",
    "지금은 {t}이에요.",
    "{t}이에요.",
    "벌써 {t}이네요.",
    "현재 시각 {t}입니다.",
    "어느덧 {t}이에요.",
    "지금 {t}이네요.",
]

MESSAGES = [
    "잘하고 있어요! 조금만 더 힘내요!",
    "집중력 최고예요! 계속 가봐요!",
    "지금 이 순간이 쌓여서 큰 성과가 돼요.",
    "잠깐 어깨 한번 펴볼까요? 그리고 다시 파이팅!",
    "물 한 모금 마시고 이어서 해봐요!",
    "한 걸음씩, 꾸준히! 정말 멋져요.",
    "당신이라면 충분히 해낼 수 있어요!",
    "눈도 잠깐 쉬어주세요. 곧 다시 집중!",
    "벌써 이만큼이나 했어요. 대단해요!",
    "포기하지 않는 당신을 응원해요!",
    "지금 하는 일에만 집중해봐요. 나머지는 나중에!",
    "완벽하지 않아도 괜찮아요. 일단 시작이 반이에요!",
    "작은 진전도 진전이에요. 잘하고 있어요!",
    "심호흡 한 번 하고, 다시 몰입해봐요.",
    "지금 흘린 땀이 나중에 큰 열매가 될 거예요.",
    "오늘 할 일 중 가장 중요한 것부터 해볼까요?",
    "스마트폰은 잠시 내려놓고, 하던 일에 집중!",
    "허리 쭉 펴고 앉아볼까요? 자세가 집중력을 만들어요.",
    "힘든 만큼 성장하고 있는 거예요. 화이팅!",
    "이 시간을 잘 보내는 당신, 정말 멋져요.",
    "조금만 더 하면 한 고비 넘겨요. 할 수 있어요!",
    "실수해도 괜찮아요. 다시 하면 되니까요.",
    "당신의 노력은 절대 배신하지 않아요.",
    "잠깐 목도 돌려주고, 다시 달려봐요!",
    "지금 이 집중을 이어가요. 응원하고 있어요!",
    "좋아요, 이 페이스 그대로 가요!",
    "쉬는 것도 능률의 일부예요. 무리하지 마세요.",
    "오늘의 나에게 박수를! 계속 이어가봐요.",
    "한 가지씩 끝내다 보면 어느새 다 끝나 있을 거예요.",
    "당신은 생각보다 훨씬 잘하고 있어요!",
]


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg.get("voice") not in VOICES.values():   # 목록에서 빠진 음성(남성·Windows 등) → 기본 음성
        cfg["voice"] = DEFAULTS["voice"]
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def cfg_int(cfg, key, lo, hi):
    """설정 파일이 망가져 있어도 멈추지 않게, 범위 안의 정수로 맞춰 돌려준다."""
    try:
        return max(lo, min(hi, int(cfg[key])))
    except (KeyError, TypeError, ValueError):
        return DEFAULTS[key]


# ---------------- 소리 ----------------
def notification_sound(custom=""):
    """설정한 파일, 없으면 앱 폴더의 첫 mp3. 둘 다 없으면 None(딩동 없이 진행)."""
    if custom and os.path.exists(custom):
        return custom
    for name in sorted(os.listdir(HERE)):
        if name.lower().endswith(".mp3"):
            return os.path.join(HERE, name)
    return None


def play_sound(path, alias="dd"):
    """mp3/wav를 끝까지 재생(MCI, 추가 설치 불필요)."""
    if path.lower().endswith(".wav"):
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return
    mci = ctypes.windll.winmm.mciSendStringW
    mci(f'close {alias}', None, 0, 0)
    if mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, 0) == 0:
        mci(f'play {alias} wait', None, 0, 0)
        mci(f'close {alias}', None, 0, 0)


# ---------------- TTS (Google 중심 + 캐시) ----------------
def api_key():
    k = os.environ.get("GOOGLE_TTS_KEY", "").strip()
    if k:
        return k
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def load_usage():
    month = time.strftime("%Y-%m")
    try:
        with open(USAGE_FILE, encoding="utf-8") as f:
            u = json.load(f)
        if u.get("month") == month:
            return u
    except (OSError, ValueError):
        pass
    return {"month": month, "chars": 0, "calls": 0}


def add_usage(chars):
    u = load_usage()
    u["chars"] += chars
    u["calls"] += 1
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(u, f)
    except OSError:
        pass


def cache_path(spec, text):
    h = hashlib.sha1(f"{spec}|{text}".encode("utf-8")).hexdigest()[:20]
    return os.path.join(CACHE_DIR, f"{h}.mp3")


def google_synth(text, voice, path):
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": "ko-KR", "name": voice},
        "audioConfig": {"audioEncoding": "MP3"},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key()}",
        data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        audio = base64.b64decode(json.load(r)["audioContent"])
    with open(path, "wb") as f:
        f.write(audio)


def edge_synth(text, voice, path):
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, voice).save(path))


_gen_lock = threading.Lock()


def _cached(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def get_clip(text, spec, cfg, allow_new=True):
    """text를 읽는 mp3 경로를 반환. 캐시에 있으면 재사용, 없으면 allow_new일 때만 생성. 실패 시 None."""
    path = cache_path(spec, text)
    if _cached(path):
        return path
    if not allow_new:
        return None
    kind, _, voice = spec.partition(":")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with _gen_lock:   # 미리 생성·알림·미리 듣기가 겹쳐도 같은 문장을 두 번 만들지 않는다
        if _cached(path):
            return path
        tmp = path + ".part"   # 다 받은 뒤에만 캐시에 넣어, 반쯤 쓰인 파일을 재생하지 않게
        try:
            if kind == "google":
                if not api_key() or load_usage()["chars"] + len(text) > cfg["monthly_char_limit"]:
                    return None
                google_synth(text, voice, tmp)
                add_usage(len(text))
            else:
                edge_synth(text, voice, tmp)
            os.replace(tmp, path)
            return path
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            return None


# ---------------- 시각 ----------------
def say_time(h, m):
    ampm = "오전" if h < 12 else "오후"
    h12 = h % 12 or 12
    return f"{ampm} {h12}시 정각" if m == 0 else f"{ampm} {h12}시 {m}분"


def to_min(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return 0


def in_api_window(cfg, minute):
    a, b = to_min(cfg["api_from"]), to_min(cfg["api_to"])
    return a <= minute <= b if a <= b else (minute >= a or minute <= b)


def time_phrase(hour, minute, template):
    return template.format(t=say_time(hour, minute))


def next_slot(n):
    """실제 시계 기준 다음 n분 단위 시각(예: 10분 → 7:00, 7:10, 7:20 ...)의 epoch."""
    lt = time.localtime()
    nxt = ((lt.tm_hour * 60 + lt.tm_min) // n + 1) * n
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, nxt, 0, 0, 0, -1))


def prefetch_todo(cfg):
    """API 시간대의 모든 시각×문구 + 응원 문구 중 아직 저장되지 않은 문장 목록."""
    spec = cfg["voice"]
    jobs = []
    for minute in range(0, 24 * 60, cfg["interval_min"]):
        if in_api_window(cfg, minute):
            jobs += [time_phrase(minute // 60, minute % 60, t) for t in TIME_TEMPLATES]
    jobs += cfg["messages"] or MESSAGES
    return [t for t in dict.fromkeys(jobs) if not _cached(cache_path(spec, t))]


def prefetch(cfg):
    """저장 안 된 문장을 미리 만들어 캐시. (생성 개수, 실패 개수) 반환."""
    spec = cfg["voice"]
    made = failed = 0
    for text in prefetch_todo(cfg):
        if get_clip(text, spec, cfg):
            made += 1
        else:
            failed += 1
            if failed >= 3:      # 계속 실패하면 중단(키/한도/네트워크 문제)
                break
    return made, failed


def work_area():
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


def monitors():
    """모든 모니터의 작업 영역(작업 표시줄 제외)을 왼쪽부터 차례로."""
    found = []

    def collect(hmon, hdc, lprc, lparam):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            w = mi.rcWork
            found.append((w.left, w.top, w.right, w.bottom))
        return 1

    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(collect), 0)
    except Exception:
        pass
    return sorted(found) or [work_area()]


def monitor_at(x, y):
    """그 점이 있는 모니터. 화면 밖이면(모니터를 뺐거나 배치가 바뀌면) 가장 가까운 모니터."""
    ms = monitors()
    for m in ms:
        if m[0] <= x < m[2] and m[1] <= y < m[3]:
            return m
    return min(ms, key=lambda m: max(m[0] - x, 0, x - m[2]) ** 2 + max(m[1] - y, 0, y - m[3]) ** 2)


def star_points(x, y, r):
    """네 갈래 반짝이 모양의 좌표."""
    pts = []
    for i in range(8):
        rad = r if i % 2 == 0 else r * 0.33
        a = i * math.pi / 4 - math.pi / 2
        pts += [x + math.cos(a) * rad, y + math.sin(a) * rad]
    return pts


class Glow:
    """알림 때 화면 테두리를 잠깐 번쩍이는 오버레이 창. 클릭은 그대로 통과한다."""

    def __init__(self, master):
        self.master = master
        self.wins = []
        self.bands = []      # (캔버스, 테두리 도형 id들) - 파티 모드에서 색을 돌린다
        self.step = 0
        self.frames = 46
        self.party = False
        self.timer = None

    def flash(self, rects=None, party=False, seconds=1.6):
        """rects 를 주면 그 영역들에, 없으면 모든 모니터에 테두리를 띄운다.
        party면 색이 돌아가며 그 시간 내내 빠르게 깜빡인다."""
        self.stop()
        self.party = party
        self.frames = max(1, int(seconds / 0.035))
        for rect in (rects or monitors()):
            try:
                self.wins.append(self._build(rect))
            except tk.TclError:
                pass
        if not self.wins:
            return
        self.step = 0
        self._tick()

    def _build(self, rect):
        l, t, r, b = rect
        gw, gh = r - l, b - t
        w = tk.Toplevel(self.master)
        w.withdraw()
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.0)
        w.attributes("-transparentcolor", KEY)
        w.config(bg=KEY)
        w.geometry(f"{gw}x{gh}+{l}+{t}")
        c = tk.Canvas(w, width=gw, height=gh, bg=KEY, highlightthickness=0)
        c.pack()
        ids = []
        for inset, width, color in GLOW_BANDS:
            half = width / 2.0
            ids.append(c.create_rectangle(inset + half, inset + half, gw - inset - half, gh - inset - half,
                                          outline=color, width=width))
        self.bands.append((c, ids))
        w.deiconify()
        w.update_idletasks()
        self._click_through(w)
        return w

    @staticmethod
    def _click_through(w):
        """테두리 위에서도 마우스가 아래 창으로 통과하고, 포커스를 빼앗지 않게 한다."""
        try:
            u = ctypes.windll.user32
            u.GetParent.argtypes, u.GetParent.restype = [wintypes.HWND], wintypes.HWND
            u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            u.GetWindowLongW.restype = wintypes.LONG
            u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
            u.SetWindowLongW.restype = wintypes.LONG
            hwnd = wintypes.HWND(u.GetParent(wintypes.HWND(w.winfo_id())) or w.winfo_id())
            ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        except Exception:
            pass

    def _tick(self):
        if not self.wins:
            return
        if self.step > self.frames:
            self.stop()
            return
        k = self.step / self.frames
        if self.party:
            a = 0.4 + 0.45 * abs(math.sin(self.step * 0.35))     # 쉬지 않고 빠르게
        else:
            a = 0.85 * math.sin(math.pi * k) * (0.55 + 0.45 * abs(math.sin(math.pi * 3 * k)))   # 세 번 맥박
        try:
            if self.party:
                for c, ids in self.bands:
                    for i, item in enumerate(ids):
                        c.itemconfig(item, outline=PARTY_COLORS[(i + self.step // 3) % len(PARTY_COLORS)])
            for w in self.wins:
                w.attributes("-alpha", round(max(0.0, min(1.0, a)), 3))
        except tk.TclError:
            self.stop()
            return
        self.step += 1
        self.timer = self.master.after(35, self._tick)

    def stop(self):
        if self.timer:                      # 끝나기 전에 다시 부르면 예약해 둔 다음 프레임부터 취소
            try:
                self.master.after_cancel(self.timer)
            except tk.TclError:
                pass
            self.timer = None
        self.bands = []
        wins, self.wins = self.wins, []
        for w in wins:
            try:
                w.destroy()
            except tk.TclError:
                pass


class GifClip:
    """효과용 GIF를 tkinter가 그릴 수 있는 프레임 목록으로 읽어 둔다(같은 파일은 한 번만).

    웹에서 받은 gif는 대개 바뀐 부분만 프레임으로 저장한다. 낱장으로 읽으면 구멍이 뚫려 보이므로
    앞 프레임 위에 겹쳐 완성한다. Pillow가 깔려 있으면 합성·축소를 맡겨 더 깔끔하게 만든다.
    """
    MAX_FRAMES = 60
    _cache = {}

    @classmethod
    def load(cls, path, box=210):
        if not path or not os.path.exists(path):
            return None
        try:
            key = (path, os.path.getmtime(path), box)
        except OSError:
            return None
        if key not in cls._cache:
            cls._cache[key] = cls._with_pillow(path, box) or cls._with_tk(path, box)
        return cls._cache[key]

    @classmethod
    def _with_pillow(cls, path, box):
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return None
        try:
            frames = []
            with Image.open(path) as im:
                for i in range(cls.MAX_FRAMES):
                    try:
                        im.seek(i)     # 순서대로 넘기면 Pillow가 프레임을 합성해 준다
                    except EOFError:
                        break
                    f = im.convert("RGBA")
                    big = max(f.size)
                    if big > box:
                        f = f.resize((max(1, round(f.width * box / big)), max(1, round(f.height * box / big))),
                                     Image.LANCZOS)
                    frames.append(ImageTk.PhotoImage(f))
            return frames or None
        except Exception:
            return None

    @classmethod
    def _with_tk(cls, path, box):
        frames, canvas = [], None
        for i in range(cls.MAX_FRAMES):
            try:
                sub = tk.PhotoImage(file=path, format=f"gif -index {i}")
            except tk.TclError:
                break
            if canvas is None:
                canvas = tk.PhotoImage(width=sub.width(), height=sub.height())
            canvas.tk.call(canvas, "copy", sub, "-compositingrule", "overlay")   # 투명한 곳은 앞 프레임 유지
            img = canvas.copy()
            big = max(img.width(), img.height())
            if big > box:              # tkinter만으로는 정수 배율 축소만 된다
                img = img.subsample(int(math.ceil(big / box)))
            frames.append(img)
        return frames or None


class Pet:
    def __init__(self):
        self.cfg = load_config()
        self.sound = notification_sound(self.cfg["sound"])
        self.root = tk.Tk()
        r = self.root
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-transparentcolor", KEY)
        r.config(bg=KEY)
        self.c = tk.Canvas(r, width=W, height=H, bg=KEY, highlightthickness=0)
        self.c.pack()

        self.talking = False
        self.bubble = ""
        self.busy = False
        self.x, self.y_show, self.y_hide, self.y = 0, 0, 0, 0
        self.drag_from = None       # 끌기 시작점 (None이면 끄는 중이 아님)
        self.dragging = False
        self.special = False        # 특별 알림 연출 중
        self.special_done = ""      # 특별 알림을 마지막으로 울린 날짜
        self.stop_special = False   # 펫을 눌러 특별 알림을 닫았는지
        self.place(*self.home())    # 저장해 둔 자리, 없으면 주 모니터 오른쪽 아래
        self.finished = False
        self.tick = 0
        self.blink_until = 0
        self.win = None
        self.next_at = next_slot(self.cfg["interval_min"])
        self.sparks = []            # 날아다니는 반짝이
        self.hopping = False        # 창을 위아래로 흔드는 중인지
        self.fx_until = 0           # 이 tick까지 효과(GIF 등)를 보여준다
        self.last_bubble = ""
        self.bubble_at = 0          # 말풍선이 뜬 tick (등장 연출용)
        self.glow = Glow(r)
        self.gif_frames = GifClip.load(self.cfg["fx_gif"])

        self.menu = tk.Menu(r, tearoff=0)
        self.menu.add_command(label="지금 나오기", command=self.pop)
        self.silent_v = tk.BooleanVar(value=self.cfg["silent"])
        self.menu.add_checkbutton(label="무음 모드 (화면으로만 알리기)", variable=self.silent_v,
                                  command=self.toggle_silent)
        self.menu.add_command(label="설정...", command=self.open_settings)
        pos_menu = tk.Menu(self.menu, tearoff=0)
        pos_menu.add_command(label="이 모니터 왼쪽 아래", command=lambda: self.snap("left"))
        pos_menu.add_command(label="이 모니터 오른쪽 아래", command=lambda: self.snap("right"))
        pos_menu.add_command(label="다음 모니터로", command=self.next_monitor)
        pos_menu.add_separator()
        pos_menu.add_command(label="기본 자리로 되돌리기", command=self.reset_pos)
        self.menu.add_cascade(label="위치 (끌어서도 옮길 수 있어요)", menu=pos_menu)
        self.menu.add_separator()
        self.menu.add_command(label="종료", command=r.destroy)
        self.c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self.c.bind("<Button-1>", self.press)
        self.c.bind("<B1-Motion>", self.drag)
        self.c.bind("<ButtonRelease-1>", self.drop)

        self.animate()
        self.schedule()

    # ---- 자리 잡기 ----
    def home(self):
        """저장해 둔 자리. 없으면 주 모니터 오른쪽 아래."""
        pos = self.cfg.get("pos")
        try:
            return int(pos[0]), int(pos[1]) - H
        except (TypeError, ValueError, IndexError):
            l, t, r, b = work_area()
            return r - W - 20, b - H

    def mon(self):
        """펫이 지금 올라가 있는 모니터의 작업 영역."""
        return monitor_at(self.x + W // 2, int(self.y) + H // 2)

    def place(self, x, y, save=False):
        """(x, y)에 있는 펫을 그 자리 모니터의 아래쪽에 붙인다. 숨었다 나오려면 화면 바닥이 필요하다."""
        ml, mt, mr, mb = monitor_at(int(x) + W // 2, int(y) + H // 2)
        self.x = max(ml, min(mr - W, int(x)))
        self.y_show = mb - H
        self.y_hide = mb - PET_TOP - PEEK
        self.y = self.y_show if self.busy else self.y_hide
        self.root.geometry(f"{W}x{H}+{self.x}+{int(self.y)}")
        if save:
            self.cfg["pos"] = [self.x, mb]
            save_config(self.cfg)

    def press(self, e):
        self.drag_from = (e.x_root, e.y_root, self.x, int(self.y))
        self.dragging = False

    def drag(self, e):
        if not self.drag_from:
            return
        x0, y0, px, py = self.drag_from
        if not self.dragging and abs(e.x_root - x0) + abs(e.y_root - y0) < 6:
            return          # 클릭하다 손이 살짝 떨린 정도는 끌기로 보지 않는다
        self.dragging = True
        self.x, self.y = px + e.x_root - x0, py + e.y_root - y0
        self.root.geometry(f"+{self.x}+{int(self.y)}")

    def drop(self, e):
        was_drag, self.dragging, self.drag_from = self.dragging, False, None
        if was_drag:
            self.place(self.x, self.y, save=True)
        elif self.special:          # 특별 알림은 눌러서 바로 닫을 수 있다
            self.stop_special = True
        elif not self.busy:
            self.pop()

    def snap(self, side):
        ml, mt, mr, mb = self.mon()
        self.place(ml + 20 if side == "left" else mr - W - 20, mb - H, save=True)

    def next_monitor(self):
        ms, cur = monitors(), self.mon()
        nl, nt, nr, nb = ms[(ms.index(cur) + 1) % len(ms)] if cur in ms else ms[0]
        left = self.x + W / 2 - cur[0] < (cur[2] - cur[0]) / 2   # 있던 쪽(왼쪽/오른쪽)을 지켜 준다
        self.place(nl + 20 if left else nr - W - 20, nb - H, save=True)

    def reset_pos(self):
        l, t, r, b = work_area()
        self.place(r - W - 20, b - H, save=True)

    def toggle_silent(self):
        """우클릭 메뉴에서 바로 무음 모드를 켜고 끈다."""
        self.cfg["silent"] = self.silent_v.get()
        save_config(self.cfg)

    # ---- 시각 효과 ----
    def fx_burst(self):
        """알림 시작 연출: 화면 테두리 번쩍 + 반짝이 한 무더기. 특별 알림은 설정을 무시하고 최대로."""
        self.fx_until = self.tick + ((SPECIAL_HOLD + 3) * 20 if self.special else 60)
        if self.special:
            self.glow.flash(party=True, seconds=SPECIAL_HOLD + 2)
            self.spawn_sparks(44, force=True)
        else:
            if self.cfg["fx_glow"]:
                self.glow.flash()
            self.spawn_sparks(18)

    def spawn_sparks(self, n, force=False):
        if not (force or self.cfg["fx_sparkle"]):
            return
        cx = W // 2
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(1.6, 4.4)
            self.sparks.append({
                "x": cx + random.uniform(-55, 55), "y": PET_TOP + random.uniform(0, 55),
                "vx": math.cos(a) * sp, "vy": math.sin(a) * sp - 2.4,
                "age": 0, "life": random.randint(14, 28),
                "r": random.uniform(3.5, 8.0),
                "col": random.choice(PARTY_COLORS if self.special else SPARK_COLORS),
            })

    def step_fx(self):
        """반짝이와 폴짝 뛰기를 한 프레임 진행한다."""
        cfg = self.cfg
        if self.talking and self.special and self.tick % 4 == 0:
            self.spawn_sparks(7, force=True)    # 특별 알림은 설정과 상관없이 계속 터뜨린다
        elif self.talking and self.tick % 10 == 0:
            self.spawn_sparks(4)                # 말하는 동안에도 계속 눈에 띄게
        alive = []
        for sp in self.sparks:
            sp["age"] += 1
            if sp["age"] > sp["life"]:
                continue
            sp["x"] += sp["vx"]
            sp["y"] += sp["vy"]
            sp["vy"] += 0.18                    # 중력
            sp["vx"] *= 0.99
            alive.append(sp)
        self.sparks = alive

        hop = 0.0
        if self.talking and (cfg["fx_hop"] or self.special) and not self.dragging:
            cycle, height = (10, 32) if self.special else (16, 18)
            ph = (self.tick % cycle) / float(cycle)   # 한 번 뛰고 그만큼 쉬고
            if ph < 0.5:
                hop = height * math.sin(math.pi * ph * 2)
        if hop or self.hopping:                 # 착지하면 원래 자리로 한 번만 되돌린다
            self.hopping = bool(hop)
            self.root.geometry(f"+{self.x}+{int(self.y - hop)}")

    # ---- 설정 창 ----
    def open_settings(self):
        if self.win and self.win.winfo_exists():
            self.win.lift()
            return
        w = self.win = tk.Toplevel(self.root)
        w.title("딩동 펫 설정")
        w.attributes("-topmost", True)
        w.resizable(False, False)
        f = ttk.Frame(w, padding=14)
        f.pack()
        cfg = self.cfg
        row = 0

        def label(text, r):
            ttk.Label(f, text=text).grid(row=r, column=0, sticky="w", pady=3)

        def hint(text, r):
            ttk.Label(f, text=text, foreground="#666").grid(row=r, column=0, columnspan=3, sticky="w")

        ttk.Label(f, foreground="#666",
                  text="펫은 마우스로 끌어서 옮길 수 있어요. 놓으면 그 모니터 아래쪽에 붙어요. "
                       "(우클릭 → 위치 메뉴로도 이동)").grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        interval = tk.IntVar(value=cfg["interval_min"])
        label("알림 간격(분)", row)
        ttk.Spinbox(f, from_=1, to=240, textvariable=interval, width=6).grid(row=row, column=1, sticky="w")
        hint("정각 기준으로 울려요 (10분 → 7:00, 7:10, 7:20 ...)", row + 1)
        row += 2

        special_v = tk.BooleanVar(value=cfg.get("special", True))
        ttk.Checkbutton(f, text=f"월요일 {SPECIAL_AT} 특별 알림: {SPECIAL_TEXT}", variable=special_v).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Button(f, text="🎉 미리 보기", command=lambda: apply() and self.pop(special=True)).grid(
            row=row, column=2, padx=4)
        row += 1

        speak_v = tk.BooleanVar(value=cfg["speak"])
        ttk.Checkbutton(f, text="음성으로 읽어주기", variable=speak_v).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=3)
        row += 1

        label("목소리", row)
        cur = next((k for k, v in VOICES.items() if v == cfg["voice"]), list(VOICES)[0])
        voice_v = tk.StringVar(value=cur)
        ttk.Combobox(f, textvariable=voice_v, values=list(VOICES), state="readonly", width=28, height=len(VOICES)).grid(
            row=row, column=1, sticky="w")

        def preview_voice():
            spec = VOICES[voice_v.get()]     # 저장하지 않아도 지금 고른 목소리로 재생
            pv_btn.config(state="disabled", text="재생 중...")

            def run():
                p = get_clip(PREVIEW_TEXT, spec, cfg)   # 목소리마다 한 번만 API 사용, 이후엔 저장된 파일
                if p:
                    play_sound(p, "pv")

                def done():
                    if not w.winfo_exists():         # 재생 중에 설정 창을 닫은 경우
                        return
                    pv_btn.config(state="normal", text="▶ 미리 듣기")
                    refresh_usage()
                    if not p:
                        messagebox.showwarning("미리 듣기", "음성을 만들지 못했어요.\nAPI 키, 월 한도, 인터넷 연결을 확인해주세요.",
                                               parent=w)
                self.root.after(0, done)
            threading.Thread(target=run, daemon=True).start()

        pv_btn = ttk.Button(f, text="▶ 미리 듣기", command=preview_voice)
        pv_btn.grid(row=row, column=2, padx=4)
        row += 1

        label("딩동 소리(mp3/wav)", row)
        sound_v = tk.StringVar(value=cfg["sound"])
        ttk.Entry(f, textvariable=sound_v, width=30).grid(row=row, column=1, sticky="w")
        ttk.Button(f, text="찾아보기", command=lambda: sound_v.set(
            filedialog.askopenfilename(parent=w, filetypes=[("소리", "*.mp3 *.wav")]) or sound_v.get())).grid(
            row=row, column=2, padx=4)
        hint("비워두면 폴더 안의 첫 mp3를 사용해요", row + 1)
        row += 2

        fxf = ttk.LabelFrame(f, text=" 소리 없이 일할 때 ", padding=8)
        fxf.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        row += 1
        silent_v = tk.BooleanVar(value=cfg["silent"])
        ttk.Checkbutton(fxf, text="무음 모드 — 딩동·음성 없이 화면 효과로만 알리기", variable=silent_v).grid(
            row=0, column=0, sticky="w")
        glow_v = tk.BooleanVar(value=cfg["fx_glow"])
        spark_v = tk.BooleanVar(value=cfg["fx_sparkle"])
        hop_v = tk.BooleanVar(value=cfg["fx_hop"])
        quiet_v = tk.IntVar(value=cfg["quiet_sec"])
        line = ttk.Frame(fxf)
        line.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(line, text="화면 테두리 번쩍", variable=glow_v).pack(side="left")
        ttk.Checkbutton(line, text="반짝이", variable=spark_v).pack(side="left", padx=8)
        ttk.Checkbutton(line, text="폴짝폴짝", variable=hop_v).pack(side="left")
        ttk.Label(line, text="    말풍선 유지").pack(side="left")
        ttk.Spinbox(line, from_=2, to=60, textvariable=quiet_v, width=4).pack(side="left", padx=4)
        ttk.Label(line, text="초").pack(side="left")
        gif_v = tk.StringVar(value=cfg["fx_gif"])
        gl = ttk.Frame(fxf)
        gl.grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(gl, text="효과 GIF").pack(side="left")
        ttk.Entry(gl, textvariable=gif_v, width=24).pack(side="left", padx=4)
        ttk.Button(gl, text="찾아보기", command=lambda: gif_v.set(
            filedialog.askopenfilename(parent=w, filetypes=[("GIF", "*.gif")]) or gif_v.get())).pack(side="left")
        ttk.Button(gl, text="지우기", command=lambda: gif_v.set("")).pack(side="left", padx=4)
        ttk.Button(gl, text="✨ 효과 미리 보기", command=lambda: apply() and self.fx_burst()).pack(side="left", padx=4)
        ttk.Label(fxf, foreground="#666",
                  text="배경이 투명한 gif를 펫 뒤에서 재생해요. 비워두면 안 씁니다.").grid(
            row=3, column=0, sticky="w", pady=(5, 0))

        ttk.Separator(f).grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        row += 1
        label("Google API 키", row)
        key_v = tk.StringVar(value=api_key())
        ttk.Entry(f, textvariable=key_v, width=30, show="*").grid(row=row, column=1, sticky="w")
        row += 1
        label("새 시각 멘트 생성 시간대", row)
        rng = ttk.Frame(f)
        rng.grid(row=row, column=1, columnspan=2, sticky="w")
        from_v, to_v = tk.StringVar(value=cfg["api_from"]), tk.StringVar(value=cfg["api_to"])
        ttk.Entry(rng, textvariable=from_v, width=6).pack(side="left")
        ttk.Label(rng, text=" ~ ").pack(side="left")
        ttk.Entry(rng, textvariable=to_v, width=6).pack(side="left")
        ttk.Label(rng, text="  (HH:MM)").pack(side="left")
        row += 1
        label("월 글자 수 한도", row)
        limit_v = tk.IntVar(value=cfg["monthly_char_limit"])
        ttk.Spinbox(f, from_=1000, to=1000000, increment=5000, textvariable=limit_v, width=9).grid(
            row=row, column=1, sticky="w")
        row += 1
        usage_lbl = ttk.Label(f, foreground="#666")
        usage_lbl.grid(row=row, column=0, columnspan=3, sticky="w")

        def refresh_usage():
            u = load_usage()
            n = len(os.listdir(CACHE_DIR)) if os.path.isdir(CACHE_DIR) else 0
            usage_lbl.config(text=f"이번 달 사용: {u['chars']:,}자 / API {u['calls']}회 · 저장된 음성 {n}개")
        refresh_usage()
        hint("시간대 밖에서는 이미 저장된 음성만 쓰고, 없으면 edge-tts로 대체해요", row + 1)
        row += 2

        label("응원 문구 (한 줄에 하나)", row)
        row += 1
        txt = tk.Text(f, width=48, height=9, wrap="word")
        txt.grid(row=row, column=0, columnspan=3)
        txt.insert("1.0", "\n".join(cfg["messages"] or MESSAGES))
        row += 1

        def apply():
            try:
                n = int(interval.get())
                if not 1 <= n <= 240:
                    raise ValueError
                lim = int(limit_v.get())
                qs = int(quiet_v.get())
                if not 2 <= qs <= 60:
                    raise ValueError
                for hhmm in (from_v.get(), to_v.get()):
                    h, m = hhmm.split(":")
                    if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
                        raise ValueError
            except (ValueError, tk.TclError):
                messagebox.showwarning("설정", "간격(1~240), 말풍선 유지 시간(2~60초), 시간대(HH:MM), 한도를 "
                                              "올바르게 입력해주세요.", parent=w)
                return False
            msgs = [l.strip() for l in txt.get("1.0", "end").splitlines() if l.strip()]
            cfg.update(interval_min=n, speak=speak_v.get(), voice=VOICES[voice_v.get()],
                       sound=sound_v.get().strip(), messages=[] if msgs == MESSAGES else msgs,
                       api_from=from_v.get().strip(), api_to=to_v.get().strip(), monthly_char_limit=lim,
                       silent=silent_v.get(), quiet_sec=qs, fx_glow=glow_v.get(), fx_sparkle=spark_v.get(),
                       fx_hop=hop_v.get(), fx_gif=gif_v.get().strip(), special=special_v.get())
            k = key_v.get().strip()
            if k != api_key():
                try:
                    with open(KEY_FILE, "w", encoding="utf-8") as kf:
                        kf.write(k)
                except OSError:
                    pass
            self.sound = notification_sound(cfg["sound"])
            self.silent_v.set(cfg["silent"])            # 우클릭 메뉴 체크 표시도 맞춰 둔다
            self.gif_frames = GifClip.load(cfg["fx_gif"])
            if cfg["fx_gif"] and not self.gif_frames:
                messagebox.showwarning("효과 GIF", "이 GIF를 읽지 못했어요.\n애니메이션 gif가 맞는지, 파일이 "
                                                 "깨지지 않았는지 확인해주세요.", parent=w)
            self.next_at = next_slot(n)
            save_config(cfg)
            return True

        def save():
            if apply():
                messagebox.showinfo("설정", "저장했어요!", parent=w)

        def do_prefetch():
            if not apply():
                return
            todo = prefetch_todo(cfg)
            if not todo:
                messagebox.showinfo("미리 생성", "이 목소리로 필요한 음성이 이미 모두 저장돼 있어요.", parent=w)
                return
            chars = sum(len(t) for t in todo)
            cost = (f"API 약 {chars:,}자를 써요. (이번 달 {load_usage()['chars']:,}자 사용 / 한도 {cfg['monthly_char_limit']:,}자)"
                    if cfg["voice"].startswith("google") else "무료 음성이라 API 비용이 들지 않아요.")
            if not messagebox.askyesno(
                    "미리 생성", f"아직 저장 안 된 시각 멘트·응원 문구 {len(todo)}개를 미리 만들까요?\n{cost}", parent=w):
                return
            btn.config(state="disabled", text="생성 중...")

            def run():
                made, failed = prefetch(cfg)

                def done():
                    if not w.winfo_exists():
                        messagebox.showinfo("미리 생성", f"새로 만든 음성 {made}개, 실패 {failed}개")
                        return
                    btn.config(state="normal", text="음성 미리 생성")
                    refresh_usage()
                    messagebox.showinfo("미리 생성", f"새로 만든 음성 {made}개, 실패 {failed}개", parent=w)
                self.root.after(0, done)
            threading.Thread(target=run, daemon=True).start()

        bar = ttk.Frame(f)
        bar.grid(row=row, column=0, columnspan=3, pady=(10, 0), sticky="e")
        btn = ttk.Button(bar, text="음성 미리 생성", command=do_prefetch)
        btn.pack(side="left", padx=4)
        ttk.Button(bar, text="펫 불러보기", command=lambda: apply() and self.pop(force=True)).pack(side="left", padx=4)
        ttk.Button(bar, text="저장", command=save).pack(side="left", padx=4)
        ttk.Button(bar, text="닫기", command=w.destroy).pack(side="left", padx=4)

    # ---- 스케줄 / 동작 ----
    def schedule(self):
        now = time.time()
        if self.special_due() and self.pop(special=True):
            self.special_done = time.strftime("%Y-%m-%d")
        elif now - self.next_at > 60:   # 절전 등으로 알림 시각을 놓쳤으면 엉뚱한 시각에 나오지 않고 다음 시각을 기다린다
            self.next_at = next_slot(self.cfg["interval_min"])
        elif not self.busy and now >= self.next_at:
            self.pop()
        self.root.after(1000, self.schedule)

    def special_due(self):
        """오늘이 그 요일이고, 그 시각부터 몇 분 안이고, 아직 안 울렸으면 울릴 차례."""
        if not self.cfg.get("special", True):
            return False
        lt = time.localtime()
        if lt.tm_wday != SPECIAL_WEEKDAY or self.special_done == time.strftime("%Y-%m-%d", lt):
            return False
        at = to_min(SPECIAL_AT)
        return at <= lt.tm_hour * 60 + lt.tm_min < at + SPECIAL_CATCHUP

    def pop(self, force=False, special=False):
        """force: 설정 창에서 직접 부를 때. 생성 시간대 밖이어도 고른 목소리로 시각 멘트를 만든다.
        special: 월요일 특별 알림. 나왔으면 True를 돌려준다."""
        if self.busy:
            return False
        self.busy = True
        self.special = special
        self.fx_burst()          # 올라오는 동안 화면 테두리가 먼저 알려준다
        self.slide(self.y_show, self.begin_special if special else (lambda: self.begin_talk(force)))
        return True

    def slide(self, target, done, step=0.25):
        dy = (target - self.y) * step
        if abs(target - self.y) < 2:
            self.y = target
            self.root.geometry(f"+{self.x}+{self.y}")
            done()
            return
        self.y += dy if abs(dy) > 1 else (1 if dy > 0 else -1)
        self.root.geometry(f"+{self.x}+{int(self.y)}")
        self.root.after(16, lambda: self.slide(target, done, step))

    def pick_time_clip(self, lt, spec, force=False):
        """이 시각의 문구를 고르고 (문구, mp3 경로 또는 None, 실제로 쓴 음성)을 반환."""
        cfg = self.cfg
        texts = [time_phrase(lt.tm_hour, lt.tm_min, t) for t in random.sample(TIME_TEMPLATES, len(TIME_TEMPLATES))]
        minute = lt.tm_hour * 60 + lt.tm_min
        allow_api = force or not spec.startswith("google") or in_api_window(cfg, minute)
        # 시간대 밖이거나, 정해진 알림 시각이 아닐 때(펫 클릭·펫 불러보기 등):
        # 이 시각에 이미 만든 문구가 있으면 재사용한다. 한 번 쓰고 말 음성을 문구마다 새로 만들지 않도록.
        if not allow_api or minute % cfg["interval_min"]:
            for text in texts:
                p = get_clip(text, spec, cfg, allow_new=False)
                if p:
                    return text, p, spec
        if allow_api:   # 정해진 알림 시각에는 무작위 문구를 그대로 써서 다양성을 유지
            p = get_clip(texts[0], spec, cfg)
            if p:
                return texts[0], p, spec
        return texts[0], get_clip(texts[0], EDGE_FALLBACK, cfg), EDGE_FALLBACK

    def prepare_clips(self, lt, msg, force):
        """시각 멘트와 응원 문구를 같은 목소리로 준비. 한쪽이라도 대체 음성이면 둘 다 대체 음성으로 맞춘다."""
        cfg = self.cfg
        ttext, tclip, used = self.pick_time_clip(lt, cfg["voice"], force)
        mclip = get_clip(msg, used, cfg)
        if not mclip and used != EDGE_FALLBACK:
            used = EDGE_FALLBACK
            tclip, mclip = get_clip(ttext, used, cfg), get_clip(msg, used, cfg)
        return ttext, [c for c in (tclip, mclip) if c]

    def begin_special(self):
        """설정을 모두 제치고 화려하게 알린다. 소리만은 무음 모드를 따른다(조용한 자리를 지키려고)."""
        cfg = self.cfg
        self.talking = True
        self.finished = False
        self.stop_special = False
        self.bubble = SPECIAL_TEXT
        quiet = cfg["silent"]

        def work():
            try:
                end = time.time() + SPECIAL_HOLD
                if not quiet:
                    # 시간대·음성 끄기 설정과 상관없이 이 문구만큼은 만든다(한 번 만들면 계속 재사용)
                    clip = get_clip(SPECIAL_TEXT, cfg["voice"], cfg) or get_clip(SPECIAL_TEXT, EDGE_FALLBACK, cfg)
                    if self.sound and not self.stop_special:
                        play_sound(self.sound)
                    for i in range(2):          # 두 번 읽어 준다
                        if clip and not self.stop_special:
                            play_sound(clip, f"sp{i}")
                while time.time() < end and not self.stop_special:
                    time.sleep(0.2)
            finally:
                self.finished = True

        threading.Thread(target=work, daemon=True).start()
        self.wait_talk()

    def begin_talk(self, force=False):
        cfg = self.cfg
        lt = time.localtime()
        msg = random.choice([m for m in cfg["messages"] if m.strip()] or MESSAGES)
        self.talking = True
        self.finished = False
        self.bubble = ""
        result = {}

        def prepare():   # 딩동이 울리는 동안 음성 준비
            result["clips"] = self.prepare_clips(lt, msg, force)

        quiet = cfg["silent"]      # 무음 모드: 딩동도 음성도 쓰지 않는다

        def work():
            try:
                gen = None
                if cfg["speak"] and not quiet:
                    gen = threading.Thread(target=prepare)
                    gen.start()
                if self.sound and not quiet:
                    play_sound(self.sound)
                if gen:
                    gen.join()
                ttext, clips = result.get("clips") or (time_phrase(lt.tm_hour, lt.tm_min, TIME_TEMPLATES[0]), [])
                self.bubble = f"{ttext}\n{msg}"
                for i, clip in enumerate(clips):
                    play_sound(clip, f"tts{i}")
                if not clips:              # 무음 모드 / 음성 끔 / 오프라인: 말풍선을 그만큼 띄워 둔다
                    time.sleep(cfg_int(cfg, "quiet_sec", 2, 60))
            finally:
                time.sleep(0.8)
                self.finished = True

        threading.Thread(target=work, daemon=True).start()
        self.wait_talk()

    def wait_talk(self):
        if self.finished:
            self.talking = False
            self.bubble = ""
            if self.special:
                self.glow.stop()
            self.next_at = next_slot(self.cfg["interval_min"])
            self.slide(self.y_hide, self.end)
        else:
            self.root.after(150, self.wait_talk)

    def end(self):
        self.busy = False
        self.special = False

    # ---- 그리기 ----
    def animate(self):
        self.tick += 1
        self.step_fx()
        self.draw()
        self.root.after(50, self.animate)

    def draw(self):
        c = self.c
        c.delete("all")
        bob = 0
        if self.busy:
            bob = int(4 * abs(((self.tick % 12) - 6) / 6.0)) if self.talking else 0
        cx, top = W // 2, PET_TOP - bob

        if self.bubble != self.last_bubble:
            self.last_bubble, self.bubble_at = self.bubble, self.tick
        if self.gif_frames and (self.talking or self.tick < self.fx_until):
            c.create_image(cx, top + 25, image=self.gif_frames[(self.tick // 2) % len(self.gif_frames)])
        if self.bubble:
            self.draw_bubble(self.bubble)

        outline, fill, ink = "#5b4636", "#ffd9a8", "#3a2a20"
        for sx in (-1, 1):   # 귀
            c.create_polygon(cx + sx * 30, top + 25, cx + sx * 62, top - 8, cx + sx * 66, top + 40,
                             fill=fill, outline=outline, width=3)
            c.create_polygon(cx + sx * 40, top + 25, cx + sx * 58, top + 5, cx + sx * 60, top + 32,
                             fill="#ffb0a8", outline="")
        c.create_oval(cx - 75, top, cx + 75, top + 125, fill=fill, outline=outline, width=3)   # 머리
        now = self.tick
        if now >= self.blink_until and random.random() < 0.02:
            self.blink_until = now + 3
        blinking = now < self.blink_until
        for sx in (-1, 1):   # 눈, 볼
            ex, ey = cx + sx * 30, top + 55
            if blinking:
                c.create_line(ex - 9, ey, ex + 9, ey, fill=ink, width=3, capstyle="round")
            else:
                c.create_oval(ex - 8, ey - 10, ex + 8, ey + 10, fill=ink, outline="")
                c.create_oval(ex - 3, ey - 6, ex + 1, ey - 2, fill="white", outline="")
            c.create_oval(ex - 22 if sx < 0 else ex + 8, ey + 12, ex - 8 if sx < 0 else ex + 22, ey + 24,
                          fill="#ffb0a8", outline="")
        c.create_oval(cx - 4, top + 68, cx + 4, top + 74, fill="#e07a7a", outline="")   # 코/입
        if self.talking and (self.tick // 3) % 2:
            c.create_oval(cx - 9, top + 78, cx + 9, top + 98, fill="#8a3b3b", outline=ink, width=2)
        else:
            c.create_arc(cx - 14, top + 66, cx, top + 90, start=200, extent=140, style="arc", outline=ink, width=2)
            c.create_arc(cx, top + 66, cx + 14, top + 90, start=200, extent=140, style="arc", outline=ink, width=2)
        for sx in (-1, 1):   # 수염
            for dy in (-4, 6):
                c.create_line(cx + sx * 45, top + 72 + dy, cx + sx * 78, top + 68 + dy * 2, fill=outline, width=2)
        for sp in self.sparks:   # 반짝이는 펫 앞에서 터진다
            k = 1 - sp["age"] / float(sp["life"])
            c.create_polygon(star_points(sp["x"], sp["y"], sp["r"] * (0.35 + 0.65 * k)),
                             fill=sp["col"], outline="")

    def draw_bubble(self, text):
        c = self.c
        x0, y0, x1, y1 = 15, 10, W - 15, 150
        r = 18
        # 뜰 때 작게 시작해 통통 튀어나온다(5프레임). 글자는 거의 다 커진 뒤에 보여준다.
        k = min(1.0, (self.tick - self.bubble_at + 1) / 5.0)
        scale = 1.0 if k >= 1 else 0.72 + 0.28 * k + 0.06 * math.sin(math.pi * k)
        ox, oy = W / 2.0, (y0 + y1) / 2.0
        # 특별 알림: 좌우로 흔들리고 테두리 색이 돌고 글자가 커졌다 작아진다
        wob = 5 * math.sin(self.tick * 0.55) if self.special else 0
        edge = PARTY_COLORS[(self.tick // 3) % len(PARTY_COLORS)] if self.special else "#5b4636"
        ink = PARTY_INK[(self.tick // 4) % len(PARTY_INK)] if self.special else "#3a2a20"
        font = ("맑은 고딕", 14 + (self.tick // 4) % 2 * 2, "bold") if self.special else ("맑은 고딕", 11, "bold")

        def sx_(x):
            return ox + (x - ox) * scale + wob

        def sy_(y):
            return oy + (y - oy) * scale

        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        c.create_polygon([sx_(v) if i % 2 == 0 else sy_(v) for i, v in enumerate(pts)],
                         smooth=True, fill="white", outline=edge, width=5 if self.special else 3)
        tx, ty = W // 2, y1
        c.create_polygon(sx_(tx - 14), sy_(ty - 1), sx_(tx + 14), sy_(ty - 1), sx_(tx), sy_(ty + 22),
                         fill="white", outline="")
        c.create_line(sx_(tx - 14), sy_(ty), sx_(tx), sy_(ty + 22), sx_(tx + 14), sy_(ty),
                      fill=edge, width=5 if self.special else 3)
        c.create_line(sx_(tx - 12), sy_(ty + 1), sx_(tx + 12), sy_(ty + 1), fill="white", width=5)
        if k > 0.7:
            c.create_text(W // 2 + wob, (y0 + y1) // 2, text=text, width=W - 60, justify="center",
                          font=font, fill=ink)


if __name__ == "__main__":
    # 한 번에 하나만 실행: 두 개가 뜨면 같은 시각에 같은 음성을 API로 두 번 만든다
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _mutex = kernel32.CreateMutexW(None, False, "DingdongPet.SingleInstance")
    if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
        sys.exit(0)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    pet = Pet()
    if "--now" in sys.argv:
        pet.root.after(500, pet.pop)
    pet.root.mainloop()

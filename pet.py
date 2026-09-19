"""딩동 펫 - 정해진 간격(정각 기준)마다 튀어나와 시간을 읽어주고 응원해주는 데스크톱 펫 (Windows).

음성: Google Cloud TTS(Chirp3 HD) 중심. 한 번 만든 mp3는 audio_cache/ 에 저장해 재사용하고,
API 사용은 사용 시간대·월 글자 수 한도로 제한한다. 실패하면 edge-tts로 대체하고, 그것도 안 되면 말풍선만 띄운다.
"""
import asyncio
import base64
import ctypes
import hashlib
import json
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

        l, t, rt, b = work_area()
        self.x = rt - W - 20
        self.y_show = b - H
        self.y_hide = b - PET_TOP - PEEK
        self.y = self.y_hide
        r.geometry(f"{W}x{H}+{self.x}+{self.y}")

        self.talking = False
        self.bubble = ""
        self.busy = False
        self.finished = False
        self.tick = 0
        self.blink_until = 0
        self.win = None
        self.next_at = next_slot(self.cfg["interval_min"])

        self.menu = tk.Menu(r, tearoff=0)
        self.menu.add_command(label="지금 나오기", command=self.pop)
        self.menu.add_command(label="설정...", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_command(label="종료", command=r.destroy)
        self.c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self.c.bind("<Button-1>", lambda e: None if self.busy else self.pop())

        self.animate()
        self.schedule()

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

        interval = tk.IntVar(value=cfg["interval_min"])
        label("알림 간격(분)", row)
        ttk.Spinbox(f, from_=1, to=240, textvariable=interval, width=6).grid(row=row, column=1, sticky="w")
        hint("정각 기준으로 울려요 (10분 → 7:00, 7:10, 7:20 ...)", row + 1)
        row += 2

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
                for hhmm in (from_v.get(), to_v.get()):
                    h, m = hhmm.split(":")
                    if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
                        raise ValueError
            except (ValueError, tk.TclError):
                messagebox.showwarning("설정", "간격(1~240), 시간대(HH:MM), 한도를 올바르게 입력해주세요.", parent=w)
                return False
            msgs = [l.strip() for l in txt.get("1.0", "end").splitlines() if l.strip()]
            cfg.update(interval_min=n, speak=speak_v.get(), voice=VOICES[voice_v.get()],
                       sound=sound_v.get().strip(), messages=[] if msgs == MESSAGES else msgs,
                       api_from=from_v.get().strip(), api_to=to_v.get().strip(), monthly_char_limit=lim)
            k = key_v.get().strip()
            if k != api_key():
                try:
                    with open(KEY_FILE, "w", encoding="utf-8") as kf:
                        kf.write(k)
                except OSError:
                    pass
            self.sound = notification_sound(cfg["sound"])
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
        if now - self.next_at > 60:     # 절전 등으로 알림 시각을 놓쳤으면 엉뚱한 시각에 나오지 않고 다음 시각을 기다린다
            self.next_at = next_slot(self.cfg["interval_min"])
        elif not self.busy and now >= self.next_at:
            self.pop()
        self.root.after(1000, self.schedule)

    def pop(self, force=False):
        """force: 설정 창에서 직접 부를 때. 생성 시간대 밖이어도 고른 목소리로 시각 멘트를 만든다."""
        if self.busy:
            return
        self.busy = True
        self.slide(self.y_show, lambda: self.begin_talk(force))

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

        def work():
            try:
                gen = None
                if cfg["speak"]:
                    gen = threading.Thread(target=prepare)
                    gen.start()
                if self.sound:
                    play_sound(self.sound)
                if gen:
                    gen.join()
                ttext, clips = result.get("clips") or (time_phrase(lt.tm_hour, lt.tm_min, TIME_TEMPLATES[0]), [])
                self.bubble = f"{ttext}\n{msg}"
                for i, clip in enumerate(clips):
                    play_sound(clip, f"tts{i}")
                if not clips:              # 음성 끔 / 오프라인: 말풍선만 잠시 보여준다
                    time.sleep(4)
            finally:
                time.sleep(0.8)
                self.finished = True

        threading.Thread(target=work, daemon=True).start()
        self.wait_talk()

    def wait_talk(self):
        if self.finished:
            self.talking = False
            self.bubble = ""
            self.next_at = next_slot(self.cfg["interval_min"])
            self.slide(self.y_hide, self.end)
        else:
            self.root.after(150, self.wait_talk)

    def end(self):
        self.busy = False

    # ---- 그리기 ----
    def animate(self):
        self.tick += 1
        self.draw()
        self.root.after(50, self.animate)

    def draw(self):
        c = self.c
        c.delete("all")
        bob = 0
        if self.busy:
            bob = int(4 * abs(((self.tick % 12) - 6) / 6.0)) if self.talking else 0
        cx, top = W // 2, PET_TOP - bob

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

    def draw_bubble(self, text):
        c = self.c
        x0, y0, x1, y1 = 15, 10, W - 15, 150
        r = 18
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        c.create_polygon(pts, smooth=True, fill="white", outline="#5b4636", width=3)
        c.create_polygon(W // 2 - 14, y1 - 1, W // 2 + 14, y1 - 1, W // 2, y1 + 22, fill="white", outline="")
        c.create_line(W // 2 - 14, y1, W // 2, y1 + 22, W // 2 + 14, y1, fill="#5b4636", width=3)
        c.create_line(W // 2 - 12, y1 + 1, W // 2 + 12, y1 + 1, fill="white", width=4)
        c.create_text(W // 2, (y0 + y1) // 2, text=text, width=W - 60, justify="center",
                      font=("맑은 고딕", 11, "bold"), fill="#3a2a20")


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

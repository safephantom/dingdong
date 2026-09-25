"""알림 연출: 화면 테두리 글로우, 반짝이, 효과 GIF."""
import math
import os
import random
import tkinter as tk

from .screen import KEY, click_through, monitors

# 화면 테두리 글로우(바깥부터 inset, 굵기, 색), 반짝이 색
GLOW_BANDS = [(0, 4, "#fff8d6"), (4, 6, "#ffd54f"), (10, 8, "#ffb300"), (18, 10, "#fb8c00")]
SPARK_COLORS = ("#ffd54f", "#fff59d", "#ffffff", "#ffb74d", "#b3e5fc", "#f8bbd0")
# 특별 알림용
PARTY_COLORS = ("#ff4081", "#ffd54f", "#40c4ff", "#69f0ae", "#b388ff", "#ff6e40")
PARTY_INK = ("#b71c1c", "#1a237e", "#1b5e20")   # 글자는 읽혀야 하니 진한 색으로만 번갈아


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
        click_through(w)
        return w

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


class Sparks:
    """펫 머리 둘레에서 터져 중력을 받아 떨어지며 작아지는 반짝이들."""

    def __init__(self):
        self.items = []

    def burst(self, n, cx, top, party=False):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(1.6, 4.4)
            self.items.append({
                "x": cx + random.uniform(-55, 55), "y": top + random.uniform(0, 55),
                "vx": math.cos(a) * sp, "vy": math.sin(a) * sp - 2.4,
                "age": 0, "life": random.randint(14, 28),
                "r": random.uniform(3.5, 8.0),
                "col": random.choice(PARTY_COLORS if party else SPARK_COLORS),
            })

    def step(self):
        alive = []
        for sp in self.items:
            sp["age"] += 1
            if sp["age"] > sp["life"]:
                continue
            sp["x"] += sp["vx"]
            sp["y"] += sp["vy"]
            sp["vy"] += 0.18                    # 중력
            sp["vx"] *= 0.99
            alive.append(sp)
        self.items = alive

    def draw(self, c):
        for sp in self.items:
            k = 1 - sp["age"] / float(sp["life"])
            c.create_polygon(star_points(sp["x"], sp["y"], sp["r"] * (0.35 + 0.65 * k)),
                             fill=sp["col"], outline="")

    def clear(self):
        self.items = []


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

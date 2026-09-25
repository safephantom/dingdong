"""펫 본체: 화면 아래에 머리만 내밀고 있다가 알림 시각이 되면 올라와 시간을 읽어주고 응원한다."""
import math
import random
import threading
import time
import tkinter as tk

from .bubble import draw_bubble
from .characters import CHARACTERS
from .config import (EDGE_FALLBACK, SPECIAL_AT, SPECIAL_CATCHUP, SPECIAL_HOLD, SPECIAL_TEXT, SPECIAL_WEEKDAY,
                     cfg_int, load_config, save_config)
from .effects import GifClip, Glow, Sparks
from .phrases import MESSAGES, TIME_TEMPLATES, next_slot, time_phrase, to_min
from .screen import KEY, monitor_at, monitors, work_area
from .settings import SettingsWindow
from .voice import get_clip, notification_sound, play_sound, prepare_clips

W, H = 300, 320
PET_TOP = 190          # 캔버스 안에서 펫 머리 꼭대기 y
PEEK = 55              # 숨어 있을 때 화면에 보이는 높이(px)


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
        self.characters = {key: look() for key, look in CHARACTERS.items()}
        self.settings = None
        self.next_at = next_slot(self.cfg["interval_min"])
        self.sparks = Sparks()      # 날아다니는 반짝이
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

    # ---- 설정 ----
    def toggle_silent(self):
        """우클릭 메뉴에서 바로 무음 모드를 켜고 끈다."""
        self.cfg["silent"] = self.silent_v.get()
        save_config(self.cfg)

    def open_settings(self):
        if self.settings and self.settings.alive():
            self.settings.win.lift()
            return
        self.settings = SettingsWindow(self)

    def config_changed(self):
        """설정 창에서 바꾼 값을 펫에 반영한다."""
        self.sound = notification_sound(self.cfg["sound"])
        self.silent_v.set(self.cfg["silent"])            # 우클릭 메뉴 체크 표시도 맞춰 둔다
        self.gif_frames = GifClip.load(self.cfg["fx_gif"])
        self.next_at = next_slot(self.cfg["interval_min"])

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
        if force or self.cfg["fx_sparkle"]:
            self.sparks.burst(n, W // 2, PET_TOP, party=self.special)

    def step_fx(self):
        """반짝이와 폴짝 뛰기를 한 프레임 진행한다."""
        cfg = self.cfg
        if self.talking and self.special and self.tick % 4 == 0:
            self.spawn_sparks(7, force=True)    # 특별 알림은 설정과 상관없이 계속 터뜨린다
        elif self.talking and self.tick % 10 == 0:
            self.spawn_sparks(4)                # 말하는 동안에도 계속 눈에 띄게
        self.sparks.step()

        hop = 0.0
        if self.talking and (cfg["fx_hop"] or self.special) and not self.dragging:
            cycle, height = (10, 32) if self.special else (16, 18)
            ph = (self.tick % cycle) / float(cycle)   # 한 번 뛰고 그만큼 쉬고
            if ph < 0.5:
                hop = height * math.sin(math.pi * ph * 2)
        if hop or self.hopping:                 # 착지하면 원래 자리로 한 번만 되돌린다
            self.hopping = bool(hop)
            self.root.geometry(f"+{self.x}+{int(self.y - hop)}")

    # ---- 알림 일정 ----
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
        if not self.cfg["special"]:
            return False
        lt = time.localtime()
        if lt.tm_wday != SPECIAL_WEEKDAY or self.special_done == time.strftime("%Y-%m-%d", lt):
            return False
        at = to_min(SPECIAL_AT)
        return at <= lt.tm_hour * 60 + lt.tm_min < at + SPECIAL_CATCHUP

    # ---- 나와서 말하기 ----
    def pop(self, force=False, special=False):
        """force: 설정 창에서 직접 부를 때. 생성 시간대 밖이어도 고른 목소리로 시각 멘트를 만든다.
        special: 특별 알림. 나왔으면 True를 돌려준다."""
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
            result["clips"] = prepare_clips(cfg, lt, msg, force)

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
        cx, top = W // 2, PET_TOP
        if self.bubble != self.last_bubble:
            self.last_bubble, self.bubble_at = self.bubble, self.tick
        if self.gif_frames and (self.talking or self.tick < self.fx_until):
            c.create_image(cx, top + 25, image=self.gif_frames[(self.tick // 2) % len(self.gif_frames)])
        if self.bubble:
            draw_bubble(c, W, self.bubble, self.tick, self.tick - self.bubble_at, self.special)
        if self.tick >= self.blink_until and random.random() < 0.02:
            self.blink_until = self.tick + 3
        blinking = self.tick < self.blink_until
        self.characters[self.cfg["character"]].draw(c, cx, top, self.tick, self.talking, blinking)
        self.sparks.draw(c)   # 반짝이는 펫 앞에서 터진다

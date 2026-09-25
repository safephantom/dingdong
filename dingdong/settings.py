"""설정 창 (우클릭 → 설정...). 저장하면 펫에 바로 반영된다."""
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .characters import CHARACTERS
from .config import PREVIEW_TEXT, SPECIAL_AT, SPECIAL_TEXT, SPECIAL_WEEKDAY, VOICES, WEEKDAYS, save_config
from .phrases import MESSAGES
from .voice import api_key, get_clip, load_usage, play_sound, prefetch, prefetch_todo, save_api_key, saved_counts


class SettingsWindow:
    def __init__(self, pet):
        self.pet = pet
        self.cfg = pet.cfg
        w = self.win = tk.Toplevel(pet.root)
        w.title("딩동 펫 설정")
        w.attributes("-topmost", True)
        w.resizable(False, False)
        self.f = ttk.Frame(w, padding=14)
        self.f.pack()
        row = self._general(0)
        row = self._quiet(row)
        row = self._voice_api(row)
        row = self._messages(row)
        self._buttons(row)

    def alive(self):
        return bool(self.win.winfo_exists())

    # ---- 화면 구성 (각각 다음 빈 줄 번호를 돌려준다) ----
    def _label(self, text, row):
        ttk.Label(self.f, text=text).grid(row=row, column=0, sticky="w", pady=3)

    def _hint(self, text, row):
        ttk.Label(self.f, text=text, foreground="#666").grid(row=row, column=0, columnspan=3, sticky="w")

    def _browse(self, var, filetypes):
        var.set(filedialog.askopenfilename(parent=self.win, filetypes=filetypes) or var.get())

    def _general(self, row):
        """캐릭터, 알림 간격, 특별 알림, 목소리, 딩동 소리."""
        f, cfg = self.f, self.cfg
        ttk.Label(f, foreground="#666",
                  text="펫은 마우스로 끌어서 옮길 수 있어요. 놓으면 그 모니터 아래쪽에 붙어요. "
                       "(우클릭 → 위치 메뉴로도 이동)").grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        self._label("캐릭터", row)
        self.char_v = tk.StringVar(value=cfg["character"])
        chf = ttk.Frame(f)
        chf.grid(row=row, column=1, columnspan=2, sticky="w")
        for key, look in CHARACTERS.items():
            ttk.Radiobutton(chf, text=look.name, value=key, variable=self.char_v).pack(side="left", padx=(0, 12))
        row += 1

        self.interval = tk.IntVar(value=cfg["interval_min"])
        self._label("알림 간격(분)", row)
        ttk.Spinbox(f, from_=1, to=240, textvariable=self.interval, width=6).grid(row=row, column=1, sticky="w")
        self._hint("정각 기준으로 울려요 (10분 → 7:00, 7:10, 7:20 ...)", row + 1)
        row += 2

        self.special_v = tk.BooleanVar(value=cfg["special"])
        ttk.Checkbutton(f, text=f"{WEEKDAYS[SPECIAL_WEEKDAY]}요일 {SPECIAL_AT} 특별 알림: {SPECIAL_TEXT}",
                        variable=self.special_v).grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Button(f, text="🎉 미리 보기", command=lambda: self.apply() and self.pet.pop(special=True)).grid(
            row=row, column=2, padx=4)
        row += 1

        self.speak_v = tk.BooleanVar(value=cfg["speak"])
        ttk.Checkbutton(f, text="음성으로 읽어주기", variable=self.speak_v).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=3)
        row += 1

        self._label("목소리", row)
        cur = next((k for k, v in VOICES.items() if v == cfg["voice"]), list(VOICES)[0])
        self.voice_v = tk.StringVar(value=cur)
        ttk.Combobox(f, textvariable=self.voice_v, values=list(VOICES), state="readonly", width=28,
                     height=len(VOICES)).grid(row=row, column=1, sticky="w")
        self.pv_btn = ttk.Button(f, text="▶ 미리 듣기", command=self.preview_voice)
        self.pv_btn.grid(row=row, column=2, padx=4)
        row += 1

        self._label("딩동 소리(mp3/wav)", row)
        self.sound_v = tk.StringVar(value=cfg["sound"])
        ttk.Entry(f, textvariable=self.sound_v, width=30).grid(row=row, column=1, sticky="w")
        ttk.Button(f, text="찾아보기", command=lambda: self._browse(self.sound_v, [("소리", "*.mp3 *.wav")])).grid(
            row=row, column=2, padx=4)
        self._hint("비워두면 폴더 안의 첫 mp3를 사용해요", row + 1)
        return row + 2

    def _quiet(self, row):
        """소리 없이 일할 때: 무음 모드와 시각 효과."""
        cfg = self.cfg
        fxf = ttk.LabelFrame(self.f, text=" 소리 없이 일할 때 ", padding=8)
        fxf.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        self.silent_v = tk.BooleanVar(value=cfg["silent"])
        ttk.Checkbutton(fxf, text="무음 모드 — 딩동·음성 없이 화면 효과로만 알리기", variable=self.silent_v).grid(
            row=0, column=0, sticky="w")
        self.glow_v = tk.BooleanVar(value=cfg["fx_glow"])
        self.spark_v = tk.BooleanVar(value=cfg["fx_sparkle"])
        self.hop_v = tk.BooleanVar(value=cfg["fx_hop"])
        self.quiet_v = tk.IntVar(value=cfg["quiet_sec"])
        line = ttk.Frame(fxf)
        line.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(line, text="화면 테두리 번쩍", variable=self.glow_v).pack(side="left")
        ttk.Checkbutton(line, text="반짝이", variable=self.spark_v).pack(side="left", padx=8)
        ttk.Checkbutton(line, text="폴짝폴짝", variable=self.hop_v).pack(side="left")
        ttk.Label(line, text="    말풍선 유지").pack(side="left")
        ttk.Spinbox(line, from_=2, to=60, textvariable=self.quiet_v, width=4).pack(side="left", padx=4)
        ttk.Label(line, text="초").pack(side="left")
        self.gif_v = tk.StringVar(value=cfg["fx_gif"])
        gl = ttk.Frame(fxf)
        gl.grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(gl, text="효과 GIF").pack(side="left")
        ttk.Entry(gl, textvariable=self.gif_v, width=24).pack(side="left", padx=4)
        ttk.Button(gl, text="찾아보기", command=lambda: self._browse(self.gif_v, [("GIF", "*.gif")])).pack(side="left")
        ttk.Button(gl, text="지우기", command=lambda: self.gif_v.set("")).pack(side="left", padx=4)
        ttk.Button(gl, text="✨ 효과 미리 보기", command=lambda: self.apply() and self.pet.fx_burst()).pack(
            side="left", padx=4)
        ttk.Label(fxf, foreground="#666",
                  text="배경이 투명한 gif를 펫 뒤에서 재생해요. 비워두면 안 씁니다.").grid(
            row=3, column=0, sticky="w", pady=(5, 0))
        return row + 1

    def _voice_api(self, row):
        """Google API 키, 새 음성을 만드는 시간대와 월 한도, 사용량."""
        f, cfg = self.f, self.cfg
        ttk.Separator(f).grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        row += 1
        self._label("Google API 키", row)
        self.key_v = tk.StringVar(value=api_key())
        ttk.Entry(f, textvariable=self.key_v, width=30, show="*").grid(row=row, column=1, sticky="w")
        self._hint("키가 없어도 [HD] 아케르나르는 함께 온 음성으로 바로 읽어줘요", row + 1)
        row += 2
        self._label("새 시각 멘트 생성 시간대", row)
        rng = ttk.Frame(f)
        rng.grid(row=row, column=1, columnspan=2, sticky="w")
        self.from_v, self.to_v = tk.StringVar(value=cfg["api_from"]), tk.StringVar(value=cfg["api_to"])
        ttk.Entry(rng, textvariable=self.from_v, width=6).pack(side="left")
        ttk.Label(rng, text=" ~ ").pack(side="left")
        ttk.Entry(rng, textvariable=self.to_v, width=6).pack(side="left")
        ttk.Label(rng, text="  (HH:MM)").pack(side="left")
        row += 1
        self._label("월 글자 수 한도", row)
        self.limit_v = tk.IntVar(value=cfg["monthly_char_limit"])
        ttk.Spinbox(f, from_=1000, to=1000000, increment=5000, textvariable=self.limit_v, width=9).grid(
            row=row, column=1, sticky="w")
        row += 1
        self.usage_lbl = ttk.Label(f, foreground="#666")
        self.usage_lbl.grid(row=row, column=0, columnspan=3, sticky="w")
        self.refresh_usage()
        self._hint("시간대 밖에서는 이미 저장된 음성만 쓰고, 없으면 edge-tts로 대체해요", row + 1)
        return row + 2

    def _messages(self, row):
        self._label("응원 문구 (한 줄에 하나)", row)
        row += 1
        self.txt = tk.Text(self.f, width=48, height=9, wrap="word")
        self.txt.grid(row=row, column=0, columnspan=3)
        self.txt.insert("1.0", "\n".join(self.cfg["messages"] or MESSAGES))
        return row + 1

    def _buttons(self, row):
        bar = ttk.Frame(self.f)
        bar.grid(row=row, column=0, columnspan=3, pady=(10, 0), sticky="e")
        self.gen_btn = ttk.Button(bar, text="음성 미리 생성", command=self.do_prefetch)
        self.gen_btn.pack(side="left", padx=4)
        ttk.Button(bar, text="펫 불러보기", command=lambda: self.apply() and self.pet.pop(force=True)).pack(
            side="left", padx=4)
        ttk.Button(bar, text="저장", command=self.save).pack(side="left", padx=4)
        ttk.Button(bar, text="닫기", command=self.win.destroy).pack(side="left", padx=4)

    # ---- 동작 ----
    def refresh_usage(self):
        u = load_usage()
        mine, bundled = saved_counts()
        self.usage_lbl.config(text=f"이번 달 사용: {u['chars']:,}자 / API {u['calls']}회 · "
                                   f"저장된 음성 {mine}개 (+ 함께 온 음성 {bundled}개)")

    def preview_voice(self):
        spec = VOICES[self.voice_v.get()]     # 저장하지 않아도 지금 고른 목소리로 재생
        self.pv_btn.config(state="disabled", text="재생 중...")

        def run():
            p = get_clip(PREVIEW_TEXT, spec, self.cfg)   # 목소리마다 한 번만 API 사용, 이후엔 저장된 파일
            if p:
                play_sound(p, "pv")

            def done():
                if not self.alive():         # 재생 중에 설정 창을 닫은 경우
                    return
                self.pv_btn.config(state="normal", text="▶ 미리 듣기")
                self.refresh_usage()
                if not p:
                    messagebox.showwarning("미리 듣기", "음성을 만들지 못했어요.\nAPI 키, 월 한도, 인터넷 연결을 확인해주세요.",
                                           parent=self.win)
            self.pet.root.after(0, done)
        threading.Thread(target=run, daemon=True).start()

    def apply(self):
        """입력값을 검사해 설정에 반영하고 저장한다. 잘못된 값이 있으면 알려주고 False."""
        w, cfg = self.win, self.cfg
        try:
            n = int(self.interval.get())
            if not 1 <= n <= 240:
                raise ValueError
            lim = int(self.limit_v.get())
            qs = int(self.quiet_v.get())
            if not 2 <= qs <= 60:
                raise ValueError
            for hhmm in (self.from_v.get(), self.to_v.get()):
                h, m = hhmm.split(":")
                if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
                    raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showwarning("설정", "간격(1~240), 말풍선 유지 시간(2~60초), 시간대(HH:MM), 한도를 "
                                          "올바르게 입력해주세요.", parent=w)
            return False
        msgs = [l.strip() for l in self.txt.get("1.0", "end").splitlines() if l.strip()]
        cfg.update(character=self.char_v.get(), interval_min=n, speak=self.speak_v.get(),
                   voice=VOICES[self.voice_v.get()], sound=self.sound_v.get().strip(),
                   messages=[] if msgs == MESSAGES else msgs,
                   api_from=self.from_v.get().strip(), api_to=self.to_v.get().strip(), monthly_char_limit=lim,
                   silent=self.silent_v.get(), quiet_sec=qs, fx_glow=self.glow_v.get(), fx_sparkle=self.spark_v.get(),
                   fx_hop=self.hop_v.get(), fx_gif=self.gif_v.get().strip(), special=self.special_v.get())
        k = self.key_v.get().strip()
        if k != api_key():
            save_api_key(k)
        self.pet.config_changed()
        if cfg["fx_gif"] and not self.pet.gif_frames:
            messagebox.showwarning("효과 GIF", "이 GIF를 읽지 못했어요.\n애니메이션 gif가 맞는지, 파일이 "
                                             "깨지지 않았는지 확인해주세요.", parent=w)
        save_config(cfg)
        return True

    def save(self):
        if self.apply():
            messagebox.showinfo("설정", "저장했어요!", parent=self.win)

    def do_prefetch(self):
        w, cfg = self.win, self.cfg
        if not self.apply():
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
        self.gen_btn.config(state="disabled", text="생성 중...")

        def run():
            made, failed = prefetch(cfg)

            def done():
                if not self.alive():
                    messagebox.showinfo("미리 생성", f"새로 만든 음성 {made}개, 실패 {failed}개")
                    return
                self.gen_btn.config(state="normal", text="음성 미리 생성")
                self.refresh_usage()
                messagebox.showinfo("미리 생성", f"새로 만든 음성 {made}개, 실패 {failed}개", parent=w)
            self.pet.root.after(0, done)
        threading.Thread(target=run, daemon=True).start()

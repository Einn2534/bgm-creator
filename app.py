"""Windows desktop UI. Tk stays on its main thread; rendering runs in a worker."""
import copy
import datetime
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import numpy as np
import pygame
import bgm

SOUND_NAMES = {"xylophone": "木琴（実音源）", "marimba": "マリンバ（実音源）", "glockenspiel": "グロッケン（実音源）",
               "pizzicato": "弦ピチカート（実音源）", "plucked_bass": "プラックベース", "soft_keys": "やわらかい鍵盤",
               "flute": "フルート風", "pulse": "矩形波", "triangle": "三角波", "percussion": "パーカッション"}


class App:
    def __init__(self, root):
        self.root = root
        root.title("Loop Atelier — BGMクリエイター")
        root.geometry("1050x830")
        root.minsize(930, 810)
        root.configure(bg="#121923")
        self.song = bgm.compose()
        self.stems = None
        self.sound = None
        self.busy = False
        self.dirty = False
        self.previous = None
        self.events = queue.Queue()
        self.audio_error = None
        try:
            pygame.mixer.init(frequency=bgm.SR, size=-16, channels=2, buffer=1024)
        except pygame.error as error:
            self.audio_error = str(error)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Yu Gothic UI", 10), background="#1c2736", foreground="#e9eff7", fieldbackground="#27364a")
        style.configure("TButton", padding=(14, 9))
        style.map("TButton", background=[("active", "#385170")])
        style.configure("TCombobox", padding=5)
        style.configure("TEntry", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#27364a")], foreground=[("readonly", "#e9eff7")])
        style.configure("TCheckbutton", padding=5)
        style.configure("Horizontal.TScale", background="#1c2736", troughcolor="#34465d")
        style.configure("Accent.TButton", background="#25796e", foreground="white")
        outer = tk.Frame(root, bg="#121923", padx=28, pady=20)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="LOOP ATELIER", font=("Segoe UI", 24, "bold"), fg="#9ae2cc", bg="#121923").pack(anchor="w")
        tk.Label(outer, text="曲を組み立てる。パートを聴く。自分のBGMに仕上げる。", font=("Yu Gothic UI", 11), fg="#a4b3c7", bg="#121923").pack(anchor="w", pady=(3, 17))
        settings = ttk.Frame(outer, padding=15)
        settings.pack(fill="x")
        self.preset = tk.StringVar(value=self.song["preset"])
        self.seed = tk.StringVar(value=str(self.song["seed"]))
        self.bpm = tk.StringVar(value=str(self.song["bpm"]))
        self.key = tk.StringVar(value="C")
        self.mode = tk.StringVar(value="長調")
        self.bars = tk.StringVar(value="8")
        fields = [("雰囲気", self.preset, list(bgm.PRESETS), 19), ("テンポ", self.bpm, None, 7),
                  ("キー", self.key, list(bgm.KEYS), 5), ("調", self.mode, ["長調", "短調"], 6),
                  ("小節", self.bars, ["4", "8", "16", "32"], 5), ("シード", self.seed, None, 9)]
        for col, (label, var, values, width) in enumerate(fields):
            ttk.Label(settings, text=label).grid(row=0, column=col, sticky="w", padx=(0, 14), pady=(0, 6))
            widget = ttk.Combobox(settings, textvariable=var, values=values, state="readonly", width=width) if values else ttk.Entry(settings, textvariable=var, width=width)
            widget.grid(row=1, column=col, sticky="ew", padx=(0, 14))
            if var is self.preset:
                widget.bind("<<ComboboxSelected>>", self.preset_changed)
            else:
                var.trace_add("write", lambda *_: self.mark_dirty())
        actions = ttk.Frame(outer, padding=(0, 13))
        actions.pack(fill="x")
        self.action_buttons = []
        for label, command in [("新しい曲を作る", self.new_song), ("設定を反映", self.apply_settings),
                               ("鼻歌を取り込む…", self.open_humming), ("設計図を開く", self.open_song),
                               ("設計図を保存", self.save_song), ("ひとつ前に戻す", self.undo)]:
            button = ttk.Button(actions, text=label, command=command)
            button.pack(side="left", padx=(0, 7))
            self.action_buttons.append(button)
        self.rows = {}
        mixer = ttk.Frame(outer, padding=15)
        mixer.pack(fill="x")
        for col, title in enumerate(("パート", "楽器", "音量", "消音", "単独試聴", "音符の変更")):
            ttk.Label(mixer, text=title).grid(row=0, column=col, sticky="w", padx=8, pady=(0, 9))
        for i, name in enumerate(bgm.PARTS, 1):
            part = self.song["parts"][name]
            instrument = tk.StringVar(value=SOUND_NAMES[part["instrument"]])
            gain = tk.DoubleVar(value=part["gain"] * 100)
            mute = tk.BooleanVar(value=part["muted"])
            ttk.Label(mixer, text=bgm.LABELS[name], width=9).grid(row=i, column=0, sticky="w", padx=8, pady=7)
            combo = ttk.Combobox(mixer, textvariable=instrument, values=list(SOUND_NAMES.values()), state="readonly", width=24)
            combo.grid(row=i, column=1, padx=8)
            combo.bind("<<ComboboxSelected>>", lambda event: self.mark_dirty())
            ttk.Scale(mixer, from_=0, to=150, variable=gain, command=lambda _, n=name: self.update_mix(n)).grid(row=i, column=2, padx=12, sticky="ew")
            ttk.Checkbutton(mixer, variable=mute, command=lambda n=name: self.update_mix(n)).grid(row=i, column=3, padx=8)
            ttk.Button(mixer, text="この音だけ", command=lambda n=name: self.play(n)).grid(row=i, column=4, padx=8)
            ttk.Button(mixer, text="作り直す", command=lambda n=name: self.regenerate(n)).grid(row=i, column=5, padx=8)
            self.rows[name] = (instrument, gain, mute)
        mixer.columnconfigure(2, weight=1)
        controls = ttk.Frame(outer, padding=(0, 16))
        controls.pack(fill="x")
        ttk.Button(controls, text="▶  ループ再生", style="Accent.TButton", command=self.play).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="■  停止", command=self.stop).pack(side="left")
        self.reverb = tk.DoubleVar(value=self.song["reverb"] * 100)
        ttk.Label(controls, text="残響").pack(side="left", padx=(22, 6))
        ttk.Scale(controls, from_=0, to=50, variable=self.reverb, length=120, command=lambda _: self.update_mix()).pack(side="left")
        self.mp3 = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="MP3も保存", variable=self.mp3).pack(side="right")
        ttk.Button(controls, text="音声を書き出す…", command=self.export_audio).pack(side="right", padx=10)
        self.canvas = tk.Canvas(outer, height=83, bg="#0e1520", highlightthickness=0)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda _: self.draw_wave())
        self.status = tk.StringVar(value="最初の曲を準備しています…")
        tk.Label(outer, textvariable=self.status, anchor="w", bg="#121923", fg="#9ae2cc", font=("Yu Gothic UI", 10), wraplength=970).pack(fill="x", pady=(12, 0))
        tk.Label(outer, text="音量・消音・残響は再生し直すと反映。楽器・テンポ・調は「設定を反映」。\n書き出し：ループWAV / 各パート / 継ぎ目確認用 / 場面転換SE / 設計図 / 音源の出典", anchor="w", justify="left", bg="#121923", fg="#8396ae", font=("Yu Gothic UI", 9)).pack(fill="x", pady=(8, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_after = root.after(100, self.poll)
        self.initial_after = root.after(150, lambda: self.render_song(self.song))

    def mark_dirty(self):
        self.dirty = True
        if not self.busy:
            self.status.set("設定が未反映です。「設定を反映」を押してください。")

    def preset_changed(self, _=None):
        bpm, mode, _, _ = bgm.PRESETS[self.preset.get()]
        self.bpm.set(str(bpm))
        self.mode.set("長調" if mode == "major" else "短調")
        self.status.set("「新しい曲を作る」でこの雰囲気の曲を作ります。")

    def collect(self, song):
        song["bpm"] = int(self.bpm.get())
        song["key"] = self.key.get()
        song["mode"] = "major" if self.mode.get() == "長調" else "minor"
        song["reverb"] = self.reverb.get() / 100
        inverse = {v: k for k, v in SOUND_NAMES.items()}
        for name, (instrument, gain, mute) in self.rows.items():
            song["parts"][name].update(instrument=inverse[instrument.get()], gain=gain.get() / 100, muted=mute.get())
        bgm.validate(song)
        return song

    def guard(self):
        if self.busy:
            return False
        return True

    def new_song(self):
        if not self.guard(): return
        try:
            song = bgm.compose(self.preset.get(), int(self.seed.get()), int(self.bars.get()))
            song.update(bpm=int(self.bpm.get()), key=self.key.get(), mode="major" if self.mode.get() == "長調" else "minor")
            bgm.validate(song)
            self.render_song(song)
        except Exception as error:
            messagebox.showerror("曲を作れません", str(error))

    def apply_settings(self):
        if not self.guard(): return
        try:
            if int(self.bars.get()) != self.song["bars"] or int(self.seed.get()) != self.song["seed"]:
                raise ValueError("小節数・シードを変えるときは「新しい曲を作る」を押してください。")
            self.render_song(self.collect(copy.deepcopy(self.song)))
        except Exception as error:
            messagebox.showerror("設定を確認してください", str(error))

    def regenerate(self, name):
        if not self.guard(): return
        if self.dirty:
            messagebox.showinfo("設定の反映", "先に「設定を反映」を押してください。")
            return
        song = copy.deepcopy(self.song)
        part = song["parts"][name]
        part["revision"] = part.get("revision", 0) + 1
        part["notes"] = bgm.make_notes(name, song["seed"] + part["revision"] * 97, song["bars"], song["preset"] == "レトロゲーム")
        part.pop("source", None)
        # Only this dry stem is rerendered. Other arrays are preserved byte for byte.
        self.render_song(song, name)

    def render_song(self, song, only=None):
        self.stop()
        self.busy = True
        self.status.set("音を組み立てています…")
        for button in self.action_buttons: button.configure(state="disabled")
        frozen = copy.deepcopy(song)
        old_stems = self.stems
        def work():
            try:
                if only and old_stems:
                    stems = dict(old_stems)
                    stems[only] = bgm.render_part(frozen, only)
                else:
                    stems = bgm.render(frozen)
                self.events.put(("render", (frozen, stems, None)))
            except Exception as error:
                self.events.put(("error", str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                self.busy = False
                for button in self.action_buttons: button.configure(state="normal")
                if event == "error":
                    self.status.set(value)
                    messagebox.showerror("処理できませんでした", value)
                elif event == "export":
                    self.status.set(f"保存しました: {value}")
                    os.startfile(str(value))
                else:
                    if self.stems is not None:
                        self.previous = (self.song, self.stems)
                    self.song, self.stems, notice = value
                    self.sync_ui()
                    seconds = len(next(iter(self.stems.values()))) / bgm.SR
                    self.status.set(notice or f"準備できました  ·  {self.song['bars']}小節 / {seconds:.1f}秒 / {self.song['bpm']} BPM  ·  ▶で試聴できます")
                    self.draw_wave()
        except queue.Empty:
            pass
        self.poll_after = self.root.after(100, self.poll)

    def sync_ui(self):
        self.preset.set(self.song["preset"])
        self.bpm.set(str(self.song["bpm"]))
        self.key.set(self.song["key"])
        self.mode.set("長調" if self.song["mode"] == "major" else "短調")
        self.seed.set(str(self.song["seed"]))
        self.bars.set(str(self.song["bars"]))
        self.reverb.set(self.song["reverb"] * 100)
        for name, (instrument, gain, mute) in self.rows.items():
            part = self.song["parts"][name]
            instrument.set(SOUND_NAMES[part["instrument"]])
            gain.set(part["gain"] * 100)
            mute.set(part["muted"])
        self.dirty = False

    def update_mix(self, name=None):
        if not hasattr(self, "rows") or self.busy: return
        if name and name in self.rows:
            _, gain, mute = self.rows[name]
            self.song["parts"][name].update(gain=gain.get() / 100, muted=mute.get())
        if hasattr(self, "reverb"):
            self.song["reverb"] = self.reverb.get() / 100
        self.draw_wave()

    def play(self, solo=None):
        if self.busy or self.stems is None: return
        if self.audio_error:
            messagebox.showerror("再生デバイス", self.audio_error + "\nWAVの書き出しは利用できます。")
            return
        self.stop()
        audio = bgm.mix(self.song, self.stems, solo)
        self.sound = pygame.sndarray.make_sound(np.ascontiguousarray(np.round(audio * 32767).astype(np.int16)))
        self.sound.play(loops=-1)
        self.status.set((bgm.LABELS[solo] + "のみ" if solo else "全パート") + "をループ再生中  ·  ■で停止")

    def stop(self):
        if pygame.mixer.get_init(): pygame.mixer.stop()
        self.sound = None

    def draw_wave(self):
        if self.stems is None: return
        audio = bgm.mix(self.song, self.stems).mean(axis=1)
        width = max(self.canvas.winfo_width(), 100)
        self.canvas.delete("all")
        for x, chunk in enumerate(np.array_split(audio, width // 3)):
            peak = float(np.max(np.abs(chunk))) * 120
            self.canvas.create_line(x * 3, 41 - peak, x * 3, 41 + peak, fill="#71cdb6", width=2)
        for bar in range(self.song["bars"]):
            x = width * bar / self.song["bars"]
            self.canvas.create_line(x, 0, x, 83, fill="#263344")
            self.canvas.create_text(x + 9, 10, text=str(bar + 1), fill="#7b8da5", font=("Segoe UI", 8))

    def undo(self):
        if not self.guard() or not self.previous: return
        self.stop()
        self.song, self.stems, self.previous = self.previous[0], self.previous[1], (self.song, self.stems)
        self.sync_ui()
        self.draw_wave()
        self.status.set("ひとつ前の曲に戻しました。もう一度押すと比較できます。")

    def open_song(self):
        if not self.guard(): return
        path = filedialog.askopenfilename(filetypes=[("曲の設計図", "*.json")])
        if path:
            try: self.render_song(bgm.load_song(path))
            except Exception as error: messagebox.showerror("開けません", str(error))

    def open_humming(self):
        if not self.guard() or self.stems is None: return
        if self.dirty:
            messagebox.showinfo("設定の反映", "先に「設定を反映」を押してください。")
            return
        self.stop()
        from humming_ui import HummingDialog
        HummingDialog(self.root, self.import_humming, self.song["bars"], self.song["bpm"])

    def import_humming(self, path, **options):
        if not self.guard() or self.stems is None: return
        self.stop()
        self.busy = True
        self.status.set("鼻歌の音程とリズムを解析しています…")
        for button in self.action_buttons: button.configure(state="disabled")
        song, stems = copy.deepcopy(self.song), dict(self.stems)
        def work():
            try:
                from humming import import_file
                imported, summary = import_file(song, path, **options)
                bgm.validate(imported)
                stems["melody"] = bgm.render_part(imported, "melody")
                notice = f"鼻歌を取り込みました  ·  {summary['detected_notes']}音 / {summary['phrase_bars']}小節 × {summary['repeats']}回  ·  ▶で伴奏と試聴できます"
                self.events.put(("render", (imported, stems, notice)))
            except Exception as error:
                self.events.put(("error", str(error)))
        threading.Thread(target=work, daemon=True).start()

    def save_song(self):
        if not self.guard() or self.stems is None: return
        if self.dirty:
            messagebox.showinfo("設定の反映", "先に「設定を反映」を押してください。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="song.json", filetypes=[("曲の設計図", "*.json")])
        if path:
            try:
                bgm.save_song(self.song, path)
                self.status.set(f"設計図を保存しました: {path}")
            except Exception as error: messagebox.showerror("保存できません", str(error))

    def export_audio(self):
        if not self.guard() or self.stems is None: return
        if self.dirty:
            messagebox.showinfo("設定の反映", "先に「設定を反映」を押してください。")
            return
        folder = filedialog.askdirectory(title="音声の保存先を選んでください")
        if not folder: return
        dest = bgm.Path(folder) / ("BGM_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        self.busy = True
        self.status.set("音声を書き出しています…")
        song, stems, mp3 = copy.deepcopy(self.song), self.stems, self.mp3.get()
        def work():
            try:
                bgm.export(song, stems, dest, mp3)
                self.events.put(("export", dest))
            except Exception as error: self.events.put(("error", str(error)))
        threading.Thread(target=work, daemon=True).start()

    def close(self):
        self.stop()
        for timer in (self.poll_after, self.initial_after):
            self.root.after_cancel(timer)
        pygame.quit()
        self.root.destroy()


if __name__ == "__main__":
    App(tk.Tk()).root.mainloop()

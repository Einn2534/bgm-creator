"""File selection and explicitly started local microphone recording."""
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from scipy.io import wavfile

import bgm
from humming import MicrophoneRecorder


class HummingDialog:
    def __init__(self, parent, on_import, bars, bpm):
        self.on_import = on_import
        self.recorder = None
        self.path = None
        self.win = tk.Toplevel(parent)
        self.win.title("鼻歌からメロディを取り込む")
        self.win.geometry("650x470")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()
        self.win.configure(bg="#1c2736")
        body = ttk.Frame(self.win, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="鼻歌を、曲のメロディに。", font=("Yu Gothic UI", 17, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(body, text=f"今の伴奏：{bars}小節 / {bpm} BPM。鼻歌だけを、はっきり一音ずつ歌ってください。\n音声はPC内で解析します。取り込みで置き換わるのはメロディだけです。", justify="left").pack(anchor="w")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=15)
        self.file_button = ttk.Button(buttons, text="音声ファイルを選ぶ…", command=self.choose_file)
        self.file_button.pack(side="left", padx=(0, 12))
        self.record_button = ttk.Button(buttons, text="● マイク録音", command=self.start_recording)
        self.record_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text="■ 録音停止", command=self.stop_recording, state="disabled")
        self.stop_button.pack(side="left")
        self.file_label = tk.StringVar(value="WAV / MP3 / M4A / FLAC など、120秒以内。マイク録音は最大60秒。")
        ttk.Label(body, textvariable=self.file_label, wraplength=600).pack(fill="x")
        options = ttk.Frame(body)
        options.pack(fill="x", pady=16)
        self.phrase = tk.StringVar(value="自動")
        self.grid = tk.StringVar(value="16分音符")
        self.pitch = tk.StringVar(value="鼻歌の音程を保持")
        choices = [("フレーズの長さ", self.phrase, ["自動"] + [str(n) + "小節" for n in (1, 2, 4, 8, 16, 32) if n <= bars], 15),
                   ("リズム補正", self.grid, ["16分音符", "8分音符", "原リズム"], 13),
                   ("音程", self.pitch, ["鼻歌の音程を保持", "曲の調に合わせる"], 21)]
        for col, (title, variable, values, width) in enumerate(choices):
            ttk.Label(options, text=title).grid(row=0, column=col, sticky="w", pady=(0, 5))
            ttk.Combobox(options, textvariable=variable, values=values, state="readonly", width=width).grid(row=1, column=col, padx=(0, 12))
        ttk.Label(body, text="前後の無音を除き、選んだ長さに合わせて曲の中で繰り返します。\n「自動」は現在のテンポから近い小節数を選びます。\n「原リズム」は鼻歌の音符の長さの比率・休符を保ちます。", justify="left").pack(anchor="w")
        self.status = tk.StringVar(value="ファイルを選ぶか、録音ボタンを押して鼻歌を録ってください。")
        ttk.Label(body, textvariable=self.status, wraplength=600, foreground="#9ae2cc").pack(fill="x", pady=(15, 10))
        self.import_button = ttk.Button(body, text="メロディとして取り込む", style="Accent.TButton", command=self.submit, state="disabled")
        self.import_button.pack(anchor="e")
        self.win.protocol("WM_DELETE_WINDOW", self.close)

    def choose_file(self):
        path = filedialog.askopenfilename(parent=self.win, title="鼻歌の音声を選んでください", filetypes=[("音声ファイル", "*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma"), ("すべてのファイル", "*.*")])
        if path:
            self.path = bgm.Path(path)
            self.file_label.set(self.path.name)
            self.status.set("準備できました。音程・リズムの補正を選んで取り込んでください。")
            self.import_button.configure(state="normal")

    def start_recording(self):
        recorder = MicrophoneRecorder()
        try:
            recorder.start()
        except Exception as error:
            messagebox.showerror("録音できません", "Windowsの既定の入力マイクと、マイクの利用許可を確認してください。\n音声ファイルからの取り込みも使えます。\n\n" + str(error), parent=self.win)
            return
        self.recorder = recorder
        self.file_button.configure(state="disabled")
        self.record_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.import_button.configure(state="disabled")
        self.tick()

    def tick(self):
        if self.recorder is None or not self.win.winfo_exists():
            return
        self.status.set(f"● 録音中 {self.recorder.frames / self.recorder.rate:.1f}秒 / 60秒 — 歌い終わったら「録音停止」")
        if self.recorder.finished:
            self.stop_recording()
        else:
            self.win.after(100, self.tick)

    def stop_recording(self):
        if self.recorder is None:
            return
        recorder, self.recorder = self.recorder, None
        try:
            data, rate = recorder.stop()
            if len(data) < rate * .15:
                raise ValueError("録音が短すぎます。0.15秒以上録音してください。")
            folder = bgm.ROOT / "outputs" / "recordings"
            folder.mkdir(parents=True, exist_ok=True)
            self.path = folder / ("humming_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".wav")
            wavfile.write(self.path, rate, np.round(np.clip(data, -1, 1) * 32767).astype(np.int16))
            self.file_label.set(self.path.name)
            self.status.set("録音をPC内に保存しました。取り込みボタンで解析します。" if not recorder.warning else "録音中に音切れがありました。必要なら録り直してください。")
        except Exception as error:
            messagebox.showerror("録音を保存できません", str(error), parent=self.win)
        finally:
            self.file_button.configure(state="normal")
            self.record_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.import_button.configure(state="normal" if self.path else "disabled")

    def submit(self):
        if not self.path or self.recorder:
            return
        options = {"phrase_bars": None if self.phrase.get() == "自動" else int(self.phrase.get().removesuffix("小節")),
                   "grid": {"16分音符": .25, "8分音符": .5, "原リズム": 0}[self.grid.get()],
                   "snap_to_key": self.pitch.get() == "曲の調に合わせる"}
        self.win.destroy()
        self.on_import(self.path, **options)

    def close(self):
        if self.recorder is not None:
            try:
                self.recorder.stop()
            finally:
                self.recorder = None
        self.win.destroy()

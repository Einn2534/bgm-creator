"""Local monophonic humming transcription using the YIN difference function.

Reference: de Cheveigne & Kawahara (2002), doi:10.1121/1.1458024.
No model downloads, network calls or source-voice samples in rendered music.
"""
from __future__ import annotations

import copy
import hashlib
import math
import shutil
import subprocess
import warnings
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, correlate, resample_poly, sosfiltfilt

RATE = 16000
MAX_SECONDS = 120


def read_audio(path):
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() == ".wav":
        if path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("音声ファイルは100MB以下にしてください。")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", wavfile.WavFileWarning)
            rate, data = wavfile.read(path)
        if data.dtype.kind == "u":
            data = (data.astype(np.float64) - 128) / 128
        elif data.dtype.kind == "i":
            data = data.astype(np.float64) / 2 ** (data.dtype.itemsize * 8 - 1)
        else:
            data = data.astype(np.float64)
        if data.ndim == 2:
            data = data.mean(axis=1)
        if len(data) / rate > MAX_SECONDS:
            raise ValueError("鼻歌は120秒以内にしてください。")
        divisor = math.gcd(rate, RATE)
        data = resample_poly(data, RATE // divisor, rate // divisor)
    else:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ValueError("WAV以外の読み込みにはffmpegが必要です。WAV形式で保存してください。")
        result = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-t", "121",
                                 "-vn", "-ac", "1", "-ar", str(RATE), "-f", "f32le", "pipe:1"],
                                capture_output=True, timeout=60,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError("音声を読み込めませんでした。WAV・MP3・M4Aなどの音声ファイルを選んでください。")
        data = np.frombuffer(result.stdout, dtype="<f4").astype(np.float64)
    if not .15 <= len(data) / RATE <= MAX_SECONDS:
        raise ValueError("0.15秒〜120秒の鼻歌を選んでください。")
    if not np.isfinite(data).all():
        raise ValueError("音声ファイルに不正な値が含まれています。")
    return data


def transcribe(data, rate=RATE):
    """Return stable {start, end, midi} notes in seconds, including real rests."""
    data = np.asarray(data, dtype=np.float64)
    if data.ndim != 1 or not np.isfinite(data).all() or rate <= 0:
        raise ValueError("有効なモノラル音声が必要です。")
    if not .15 <= len(data) / rate <= MAX_SECONDS:
        raise ValueError("0.15秒〜120秒の鼻歌を選んでください。")
    if rate != RATE:
        divisor = math.gcd(int(rate), RATE)
        data = resample_poly(data, RATE // divisor, int(rate) // divisor)
    data = data - np.median(data)
    peak = float(np.max(np.abs(data)))
    if peak < 1e-5:
        raise ValueError("音程を検出できませんでした。マイクの音量を確認して、鼻歌を録り直してください。")
    data /= peak
    data = sosfiltfilt(butter(3, [60, 1800], btype="bandpass", fs=RATE, output="sos"), data)
    hop, window, maxlag = 160, 1024, int(RATE / 65)
    minlag = int(RATE / 1000)
    padded = np.pad(data, (window // 2, window + maxlag))
    count = math.ceil(len(data) / hop)
    rms = np.array([np.sqrt(np.mean(padded[i * hop + window // 2 - 160:i * hop + window // 2 + 160] ** 2)) for i in range(count)])
    gate = max(.006, float(np.percentile(rms, 90)) * .09)
    pitches = np.full(count, np.nan)
    for i in np.flatnonzero(rms > gate):
        frame = padded[i * hop:i * hop + window + maxlag]
        energy = np.r_[0., np.cumsum(frame * frame)]
        cross = correlate(frame, frame[:window], mode="valid", method="fft")
        difference = np.maximum(energy[window] + energy[window:window + maxlag + 1] - energy[:maxlag + 1] - 2 * cross, 0)
        cmnd = np.ones(maxlag + 1)
        cmnd[1:] = difference[1:] * np.arange(1, maxlag + 1) / np.maximum(np.cumsum(difference[1:]), 1e-12)
        lag = minlag
        while lag < maxlag:
            if cmnd[lag] < .17:
                while lag + 1 <= maxlag and cmnd[lag + 1] < cmnd[lag]:
                    lag += 1
                break
            lag += 1
        if lag == maxlag:
            lag = minlag + int(np.argmin(cmnd[minlag:]))
        if cmnd[lag] > .28:
            continue
        refined = float(lag)
        if 0 < lag < maxlag:
            a, b, c = cmnd[lag - 1:lag + 2]
            denominator = a - 2 * b + c
            if abs(denominator) > 1e-10:
                refined += float(np.clip(.5 * (a - c) / denominator, -.5, .5))
        frequency = RATE / refined
        if 65 <= frequency <= 1000:
            pitches[i] = 69 + 12 * np.log2(frequency / 440)
    # Median filter voiced frames only: don't bridge intentional silent gaps.
    smoothed = pitches.copy()
    for i in np.flatnonzero(np.isfinite(pitches)):
        local = pitches[max(0, i - 2):i + 3]
        smoothed[i] = np.nanmedian(local)
    labels = np.where(np.isfinite(smoothed), np.rint(np.nan_to_num(smoothed)), -1).astype(int)
    # Short pitch glitches inside a sustained note should not retrigger it.
    def runs(values):
        bounds = np.r_[0, np.flatnonzero(np.diff(values) != 0) + 1, len(values)]
        return [(int(a), int(b), int(values[a])) for a, b in zip(bounds[:-1], bounds[1:])]
    for a, b, pitch in runs(labels):
        if b - a <= 3 and a > 0 and b < count and labels[a - 1] == labels[b] and labels[a - 1] >= 0:
            labels[a:b] = labels[a - 1]
    notes = []
    for a, b, pitch in runs(labels):
        if pitch < 0 or (b - a) * hop / RATE < .07:
            continue
        # Exclude out-of-voice high/low detections and unstable noise segments.
        if 36 <= pitch <= 84:
            notes.append({"start": round(a * hop / RATE, 4), "end": round(min(b * hop / RATE, len(data) / RATE), 4), "midi": pitch})
    if not notes:
        raise ValueError("安定した音程を検出できませんでした。伴奏を入れず、一音ずつ少し長めに歌ってください。")
    return notes


def apply_melody(song, detected, phrase_bars=None, grid=.25, snap_to_key=False):
    """Replace only melody, repeating a fitted phrase; preserve accompaniment."""
    import bgm
    bgm.validate(song)
    if grid not in (0, .25, .5):
        raise ValueError("リズム補正の指定が不正です。")
    if not detected:
        raise ValueError("取り込める音符がありません。")
    span = detected[-1]["end"] - detected[0]["start"]
    if span <= 0:
        raise ValueError("鼻歌の長さを読み取れませんでした。")
    choices = [n for n in (1, 2, 4, 8, 16, 32) if n <= song["bars"]]
    if phrase_bars is None:
        natural_bars = span * song["bpm"] / 240
        phrase_bars = min(choices, key=lambda n: abs(math.log2(n / natural_bars)))
    if phrase_bars not in choices:
        raise ValueError("鼻歌の長さは曲の小節数以下にしてください。")
    phrase_beats = phrase_bars * 4
    adjusted = []
    start_time = detected[0]["start"]
    for item in detected:
        start = (item["start"] - start_time) / span * phrase_beats
        end = (item["end"] - start_time) / span * phrase_beats
        if grid:
            start = round(start / grid) * grid
            end = max(start + grid, round(end / grid) * grid)
        if start >= phrase_beats:
            continue
        midi = int(item["midi"])
        candidates = [(degree, octave) for octave in range(max(0, midi // 12 - 2), min(8, midi // 12) + 1) for degree in range(7)]
        degree, octave = min(candidates, key=lambda d: abs(bgm.midi_pitch(song, {"degree": d[0], "octave": d[1]}) - midi))
        accidental = 0 if snap_to_key else midi - bgm.midi_pitch(song, {"degree": degree, "octave": octave})
        note = {"beat": round(start, 6), "duration": round(min(end, phrase_beats) - start, 6),
                "degree": degree, "octave": octave, "velocity": .7}
        if accidental:
            note["accidental"] = accidental
        # Quantization may collapse two onsets; keep the later intended pitch.
        if adjusted and adjusted[-1]["beat"] == note["beat"]:
            adjusted[-1] = note
        else:
            adjusted.append(note)
    for index, note in enumerate(adjusted[:-1]):
        note["duration"] = min(note["duration"], adjusted[index + 1]["beat"] - note["beat"])
    result = copy.deepcopy(song)
    notes = []
    for repeat in range(song["bars"] // phrase_bars):
        for note in adjusted:
            remaining = note["duration"]
            offset = note["beat"] + repeat * phrase_beats
            # The score format allows up to 16 beats per event.
            while remaining >= .01:
                duration = min(remaining, 16.)
                notes.append(dict(note, beat=round(offset, 6), duration=round(duration, 6)))
                remaining -= duration
                offset += duration
    if not notes:
        raise ValueError("取り込める音符がありません。リズム補正を変えてください。")
    result["parts"]["melody"]["notes"] = notes
    result["parts"]["melody"]["muted"] = False
    result["parts"]["melody"].pop("revision", None)
    return result, {"detected_notes": len(detected), "phrase_bars": phrase_bars,
                    "repeats": song["bars"] // phrase_bars, "grid": grid, "snap_to_key": snap_to_key}


def import_file(song, path, **options):
    path = Path(path)
    detected = transcribe(read_audio(path))
    result, summary = apply_melody(song, detected, **options)
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    result["parts"]["melody"]["source"] = {"kind": "humming", "file": path.name,
        "sha256": digest, "algorithm": "YIN", **summary}
    return result, summary


class MicrophoneRecorder:
    """The microphone is opened only by an explicit record-button action."""
    def __init__(self):
        self.stream = None
        self.frames = 0
        self.rate = 0
        self.data = None
        self.warning = ""

    def start(self):
        import sounddevice as sd
        self.rate = int(sd.query_devices(kind="input")["default_samplerate"])
        if not 8000 <= self.rate <= 192000:
            raise ValueError("マイクのサンプルレートに対応していません。")
        self.data = np.empty((self.rate * 60, 1), dtype=np.float32)
        self.frames = 0
        self.warning = ""
        def capture(indata, frames, timing, status):
            if status:
                self.warning = str(status)
            amount = min(frames, len(self.data) - self.frames)
            self.data[self.frames:self.frames + amount] = indata[:amount]
            self.frames += amount
            if self.frames >= len(self.data):
                raise sd.CallbackStop
        self.stream = sd.InputStream(samplerate=self.rate, channels=1, dtype="float32", callback=capture)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            self.stream = None
            raise

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None
        data = self.data[:self.frames, 0].copy() if self.data is not None else np.empty(0, dtype=np.float32)
        self.data = None
        return data, self.rate

    @property
    def finished(self):
        return self.stream is not None and not self.stream.active

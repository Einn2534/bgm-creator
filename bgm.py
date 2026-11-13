"""Deterministic, editable loop composer and offline stereo renderer."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parent
SR = 44100
PARTS = ("rhythm", "bass", "chords", "melody", "sparkle")
LABELS = dict(zip(PARTS, ("リズム", "ベース", "コード", "メロディ", "飾り")))
INSTRUMENTS = ("xylophone", "marimba", "glockenspiel", "pizzicato", "plucked_bass", "soft_keys", "flute", "pulse", "triangle", "percussion")
PRESETS = {
    "明るい散歩道": (132, "major", "xylophone", "pizzicato"),
    "静かな作業部屋": (86, "major", "marimba", "soft_keys"),
    "少し切ない夕暮れ": (96, "minor", "flute", "soft_keys"),
    "レトロゲーム": (144, "major", "pulse", "pulse"),
}
KEYS = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def compose(preset="明るい散歩道", seed=42, bars=8):
    bpm, mode, lead, chord_sound = PRESETS[preset]
    chip = preset == "レトロゲーム"
    song = {"version": 1, "title": preset, "preset": preset, "seed": int(seed), "bpm": bpm,
            "key": "C", "mode": mode, "bars": int(bars), "reverb": .12,
            "master": .8, "parts": {}}
    sounds = ("percussion", "triangle" if chip else "plucked_bass", chord_sound, lead, "glockenspiel")
    for part, sound, gain, pan in zip(PARTS, sounds, (.65, .78, .50, .70, .28), (0, -.12, -.25, .15, .40)):
        song["parts"][part] = {"instrument": sound, "gain": gain, "pan": pan, "muted": part == "sparkle" and chip,
                                 "notes": make_notes(part, int(seed), int(bars), chip)}
    return song


def make_notes(part, seed, bars, chip=False):
    rng = np.random.default_rng(seed + PARTS.index(part) * 10007)
    notes = []
    motif = rng.choice([0, 1, 2, 4], size=8)
    def add(beat, duration, degree, octave, velocity=.75):
        notes.append({"beat": float(beat), "duration": float(duration), "degree": int(degree),
                      "octave": int(octave), "velocity": round(float(velocity), 4)})
    for bar in range(bars):
        root = [0, 5, 3, 4][bar % 4]
        start = bar * 4
        if part == "rhythm":
            offbeat = float(rng.choice([.5, .5, .75]))
            for step in range(8):
                # One noise channel for the chip preset; drum IDs: kick, snare, hat, wood.
                drum = (0 if step % 4 == 0 else 1 if step % 4 == 2 else 2) if chip else (3 if step % 2 == 0 else 2)
                add(start + step * .5 + (offbeat - .5 if step % 2 else 0), .16, drum, 0,
                    rng.uniform(.56, .70) if step % 2 == 0 else rng.uniform(.24, .38))
        elif part == "bass":
            pickup = float(rng.choice([2.5, 3, 3.5]))
            for beat, degree in [(0, root), (1.5, root), (pickup, root + int(rng.choice([0, 4])))]:
                add(start + beat, .65, degree, 2, .73 if beat == 0 else .55)
        elif part == "chords":
            if chip:
                for step in range(16):
                    add(start + step / 4, .17, root + [0, 2, 4, 2][step % 4], 4, .32)
            else:
                for beat in (0, float(rng.choice([1.5, 2])), 3):
                    for degree in (root, root + 2, root + 4):
                        add(start + beat, .42, degree, 3, .55)
        elif part == "melody":
            for step in range(6):
                if step == 3 and bar % 2:
                    continue
                degree = root + int(motif[(step + (bar % 2) * 2) % 8])
                # Reuse a motif, end phrases on chord tones and leave breathing room.
                if step == 5:
                    degree = root + (2 if bar % 2 == 0 else 0)
                add(start + step * .5 + (.5 if bar % 2 else 0), .36 if step != 5 else .65,
                    degree, 4 if song_low(seed) else 5, rng.uniform(.55, .78))
        else:
            if bar % 2 == 0:
                add(start, .6, root, 6, .55)
                add(start + float(rng.choice([2, 2.5, 3])), .5, root + int(rng.choice([2, 4])), 5, .40)
    return notes


def song_low(seed):
    return seed % 3 == 0


def validate(song):
    if song.get("version") != 1:
        raise ValueError("設計図のバージョンに対応していません")
    if not 40 <= float(song["bpm"]) <= 240 or int(song["bars"]) not in (4, 8, 16, 32):
        raise ValueError("テンポは40〜240、小節数は4/8/16/32にしてください")
    if song["key"] not in KEYS or song["mode"] not in ("major", "minor"):
        raise ValueError("調の指定が不正です")
    if not 0 <= float(song["reverb"]) <= .5 or not 0 <= float(song["master"]) <= 1:
        raise ValueError("残響またはマスター音量の範囲外です")
    for name in PARTS:
        part = song["parts"][name]
        if part["instrument"] not in INSTRUMENTS or not 0 <= float(part["gain"]) <= 1.5 or not -1 <= float(part["pan"]) <= 1:
            raise ValueError(f"{name}: 楽器・音量・定位の指定が不正です")
        if len(part["notes"]) > 10000:
            raise ValueError("音符が多すぎます")
        for n in part["notes"]:
            vals = [float(n[k]) for k in ("beat", "duration", "degree", "octave", "velocity")]
            if not all(math.isfinite(v) for v in vals):
                raise ValueError("音符に有限数でない値があります")
            if not (0 <= vals[0] < song["bars"] * 4 and .01 <= vals[1] <= 16 and -14 <= vals[2] <= 28 and 0 <= vals[3] <= 8 and 0 <= vals[4] <= 1):
                raise ValueError("音符の指定が範囲外です")
            accidental = n.get("accidental", 0)
            if not isinstance(accidental, int) or not -1 <= accidental <= 1:
                raise ValueError("臨時記号は-1/0/1にしてください")


def midi_pitch(song, note):
    scale = [0, 2, 4, 5, 7, 9, 11] if song["mode"] == "major" else [0, 2, 3, 5, 7, 8, 10]
    octaves, degree = divmod(note["degree"], 7)
    return (note["octave"] + 1 + octaves) * 12 + KEYS[song["key"]] + scale[degree] + note.get("accidental", 0)


@lru_cache(maxsize=32)
def sample_data(instrument):
    manifest_path = ROOT / "assets" / "samples" / "manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = []
    for entry in manifest.get("samples", []):
        path = manifest_path.parent / entry["file"]
        if entry["instrument"] != instrument or not path.exists():
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"音源のチェックサムが一致しません: {path.name}")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=wavfile.WavFileWarning, message="Chunk .* not understood.*")
            rate, data = wavfile.read(path)
        if data.dtype.kind == "i":
            data = data.astype(np.float32) / float(2 ** (data.dtype.itemsize * 8 - 1))
        else:
            data = data.astype(np.float32)
        if data.ndim == 2:
            data = data.mean(axis=1)
        active = np.flatnonzero(np.abs(data) > np.max(np.abs(data)) * .008)
        if len(active):
            data = data[max(0, active[0] - int(rate * .002)):active[-1] + 1]
        data /= max(float(np.max(np.abs(data))), .001)
        result.append((entry["midi"], rate, data))
    return result


def note_audio(instrument, midi, duration, drum=0):
    samples = sample_data(instrument)
    if samples:
        root, rate, data = min(samples, key=lambda item: abs(item[0] - midi))
        speed = 2 ** ((midi - root) / 12) * rate / SR
        size = min(int(len(data) / speed), int((duration + .6) * SR))
        y = np.interp(np.arange(size) * speed, np.arange(len(data)), data).astype(np.float32)
        tail = min(int(.055 * SR), len(y))
        y[-tail:] *= np.linspace(1, 0, tail)
        y[:min(88, len(y))] *= np.linspace(0, 1, min(88, len(y)))
        return y * .23
    length = duration + (.35 if instrument not in ("pulse", "triangle", "flute") else .045)
    t = np.arange(max(2, int(length * SR)), dtype=np.float32) / SR
    freq = 440 * 2 ** ((midi - 69) / 12)
    phase = 2 * np.pi * freq * t
    if instrument == "percussion":
        rng = np.random.default_rng(1701 + drum)
        noise = rng.standard_normal(len(t)).astype(np.float32)
        if drum == 0:
            y = np.sin(2 * np.pi * (48 * t + 5 * (1 - np.exp(-t * 25)))) * np.exp(-t * 22)
        elif drum == 1:
            y = (noise * .6 + .3 * np.sin(2 * np.pi * 170 * t)) * np.exp(-t * 28)
        elif drum == 2:
            y = np.r_[0, np.diff(noise)] * np.exp(-t * 65) * .20
        else:
            y = (np.sin(2 * np.pi * 730 * t) + .5 * np.sin(2 * np.pi * 1120 * t)) * np.exp(-t * 48)
        y *= .25
    elif instrument in ("pulse", "triangle"):
        y = np.zeros_like(t)
        for harmonic in range(1, min(40, int((SR / 2 - 100) / max(freq, 1))) + 1, 2):
            amp = 1 / harmonic if instrument == "pulse" else (-1) ** ((harmonic - 1) // 2) / harmonic ** 2
            y += amp * np.sin(phase * harmonic)
        y *= .15 * np.exp(-t * 2)
    elif instrument in ("plucked_bass", "pizzicato", "soft_keys"):
        y = sum(np.sin(phase * h) * np.exp(-t * (3 + h * 1.8)) / h ** 1.5 for h in range(1, 7)) * .25
    elif instrument == "flute":
        y = (np.sin(phase + .014 * np.sin(2 * np.pi * 5 * t)) + .14 * np.sin(phase * 2)) * .20
        y *= np.minimum(t / .04, 1) * np.exp(-t * 1.8)
    else:
        ratio = 2.76 if instrument == "glockenspiel" else 3.98
        decay = 2 if instrument == "glockenspiel" else 8
        y = (np.sin(phase) * np.exp(-t * decay) + .28 * np.sin(phase * ratio) * np.exp(-t * 18)) * .24
    attack = min(130, len(t))
    y[:attack] *= np.linspace(0, 1, attack)
    release = min(int(.025 * SR), len(t))
    y[-release:] *= np.linspace(1, 0, release)
    return y.astype(np.float32)


def render_part(song, name):
    part = song["parts"][name]
    seconds_per_beat = 60 / song["bpm"]
    size = round(song["bars"] * 4 * seconds_per_beat * SR)
    mono = np.zeros(size, dtype=np.float32)
    cache = {}
    for note in part["notes"]:
        midi = midi_pitch(song, note) if name != "rhythm" else 60
        key = (part["instrument"], midi, note["duration"], note["degree"] if name == "rhythm" else 0)
        if key not in cache:
            cache[key] = note_audio(part["instrument"], midi, note["duration"] * seconds_per_beat, key[3])
        audio = cache[key] * note["velocity"]
        offset = round(note["beat"] * seconds_per_beat * SR)
        # Fold the decay into the beginning: the exported file is one exact musical period.
        for p in range(0, len(audio), size):
            chunk = audio[p:p + size]
            first = min(len(chunk), size - offset)
            mono[offset:offset + first] += chunk[:first]
            if first < len(chunk):
                mono[:len(chunk) - first] += chunk[first:]
    # Keep dry stems independent of gain, mute and all other parts.
    return mono


def render(song):
    validate(song)
    return {name: render_part(song, name) for name in PARTS}


def mix(song, stems, solo=None):
    size = len(next(iter(stems.values())))
    stereo = np.zeros((size, 2), dtype=np.float32)
    for name, data in stems.items():
        part = song["parts"][name]
        if (solo is not None and name != solo) or (solo is None and part.get("muted", False)):
            continue
        pan = (part["pan"] + 1) * np.pi / 4
        stereo += data[:, None] * np.array([np.cos(pan), np.sin(pan)], dtype=np.float32) * part["gain"]
    wet = song["reverb"]
    if wet:
        dry = stereo.copy()
        for delay, amount in ((.073, .32), (.131, .24), (.197, .18), (.293, .13)):
            stereo += np.roll(dry[:, ::-1], round(delay * SR), axis=0) * wet * amount
    stereo *= song["master"]
    peak = float(np.max(np.abs(stereo)))
    if peak > .97:
        stereo *= .97 / peak
    return stereo


def save_song(song, path):
    validate(song)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(song, ensure_ascii=False, indent=2), encoding="utf-8")


def load_song(path):
    song = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    validate(song)
    return song


def write_wav(path, audio):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(path, SR, np.round(np.clip(audio, -1, 1) * 32767).astype(np.int16))


def export(song, stems, destination, mp3=False):
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    audio = mix(song, stems)
    write_wav(dest / "loop.wav", audio)
    # 3 consecutive loops for hearing both boundaries without player restart latency.
    write_wav(dest / "loop_check.wav", np.tile(audio, (3, 1)))
    for name in PARTS:
        write_wav(dest / f"{name}.wav", mix(song, stems, solo=name))
    # Last bar, then a short tail and fade: a finite transition cue.
    size = round(4 * 60 / song["bpm"] * SR)
    cue = np.concatenate((audio[-size:], audio[:int(.45 * SR)])).copy()
    fade = min(int(.45 * SR), len(cue))
    cue[-fade:] *= np.linspace(1, 0, fade)[:, None]
    cue[:220] *= np.linspace(0, 1, 220)[:, None]
    write_wav(dest / "transition.wav", cue)
    save_song(song, dest / "song.json")
    manifest = ROOT / "assets" / "samples" / "manifest.json"
    records = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {"samples": []}
    instruments = {p["instrument"] for p in song["parts"].values()}
    records["samples"] = [s for s in records["samples"] if s["instrument"] in instruments and (manifest.parent / s["file"]).exists()]
    records["synthesized_instruments"] = sorted(i for i in instruments if not sample_data(i))
    records["song_sha256"] = hashlib.sha256((dest / "song.json").read_bytes()).hexdigest()
    if song["parts"]["melody"].get("source"):
        records["melody_source"] = song["parts"]["melody"]["source"]
    records["format"] = "44100 Hz, stereo, PCM 16-bit"
    records["boundary_step"] = float(np.max(np.abs(audio[-1] - audio[0])))
    (dest / "sources.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    if mp3:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("WAVは保存しました。MP3にはffmpegが必要です")
        subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(dest / "loop.wav"), "-codec:a", "libmp3lame", "-q:a", "2", str(dest / "loop.mp3")], check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return dest / "loop.wav"


def main():
    parser = argparse.ArgumentParser(description="ループBGM制作ツール")
    parser.add_argument("--song", type=Path)
    parser.add_argument("--preset", choices=list(PRESETS), default=next(iter(PRESETS)))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bars", type=int, default=8)
    parser.add_argument("--bpm", type=int)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "demo")
    parser.add_argument("--mp3", action="store_true")
    parser.add_argument("--hum", type=Path, help="鼻歌の音声ファイル")
    parser.add_argument("--hum-bars", type=int, help="鼻歌を何小節に合わせるか（省略時は自動）")
    parser.add_argument("--hum-grid", type=float, choices=[0, .25, .5], default=.25)
    parser.add_argument("--hum-snap", action="store_true", help="曲の調に音程を合わせる")
    args = parser.parse_args()
    song = load_song(args.song) if args.song else compose(args.preset, args.seed, args.bars)
    if args.bpm:
        song["bpm"] = args.bpm
    if args.hum:
        from humming import import_file
        song, summary = import_file(song, args.hum, phrase_bars=args.hum_bars, grid=args.hum_grid, snap_to_key=args.hum_snap)
        print(f"Humming: {summary['detected_notes']} notes / {summary['phrase_bars']} bars")
    print(export(song, render(song), args.out, args.mp3))


if __name__ == "__main__":
    main()

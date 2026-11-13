import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import wavfile

import bgm
import humming


def fake_hum(pitches=(60, 62, 64, 67), rate=16000, gap=.12, noise=.003):
    """Harmonic-rich, vibrato humming fixture with silence, not pure sine notes."""
    rng = np.random.default_rng(911)
    chunks = [np.zeros(int(rate * .28))]
    for midi in pitches:
        t = np.arange(int(rate * .48)) / rate
        frequency = 440 * 2 ** ((midi - 69) / 12)
        phase = np.cumsum(2 * np.pi * frequency * (1 + .007 * np.sin(2 * np.pi * 5 * t)) / rate)
        tone = .19 * np.sin(phase) + .30 * np.sin(phase * 2) + .11 * np.sin(phase * 3)
        envelope = np.minimum(t / .025, 1) * np.minimum((.48 - t) / .035, 1)
        chunks.extend((tone * envelope, np.zeros(int(rate * gap))))
    chunks.append(np.zeros(int(rate * .25)))
    data = np.concatenate(chunks)
    return (data + rng.normal(0, noise, len(data))).astype(np.float32)


class HummingTests(unittest.TestCase):
    def test_harmonics_vibrato_and_rests(self):
        notes = humming.transcribe(fake_hum())
        self.assertEqual([n["midi"] for n in notes], [60, 62, 64, 67], notes)
        self.assertAlmostEqual(notes[0]["start"], .28, delta=.06)
        for first, second in zip(notes, notes[1:]):
            self.assertGreater(second["start"] - first["end"], .04)

    def test_low_high_and_repeated_pitch(self):
        for pitches in [(43, 48, 55), (72, 76, 79), (60, 60, 62)]:
            notes = humming.transcribe(fake_hum(pitches))
            self.assertEqual([n["midi"] for n in notes], list(pitches), notes)

    def test_silence_noise_and_invalid_rejected(self):
        for data in (np.zeros(16000), np.random.default_rng(4).normal(0, .2, 16000), np.array([np.nan] * 16000)):
            with self.assertRaises(ValueError): humming.transcribe(data)

    def test_fit_chromatic_repeat_and_preserve_accompaniment(self):
        song = bgm.compose(bars=8)
        before = copy.deepcopy(song)
        notes = [{"start": .3, "end": .8, "midi": 61}, {"start": 1., "end": 1.8, "midi": 66}]
        result, report = humming.apply_melody(song, notes, phrase_bars=2)
        bgm.validate(result)
        self.assertEqual(report["repeats"], 4)
        self.assertEqual(len(result["parts"]["melody"]["notes"]), 8)
        self.assertEqual([bgm.midi_pitch(result, n) for n in result["parts"]["melody"]["notes"][:2]], [61, 66])
        self.assertEqual(song, before)
        for name in bgm.PARTS:
            if name != "melody": self.assertEqual(result["parts"][name], song["parts"][name])
        snapped, _ = humming.apply_melody(song, notes, phrase_bars=2, snap_to_key=True)
        self.assertTrue(all(n.get("accidental", 0) == 0 for n in snapped["parts"]["melody"]["notes"]))

    def test_file_resample_save_reload_render_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "鼻歌.wav"
            mono = fake_hum(rate=44100)
            stereo = np.column_stack([mono, mono * .8])
            wavfile.write(path, 44100, (stereo * 32767).astype(np.int16))
            song, report = humming.import_file(bgm.compose(bars=4), path)
            self.assertEqual(report["detected_notes"], 4)
            self.assertEqual(song["parts"]["melody"]["source"]["file"], path.name)
            stems = bgm.render(song)
            dest = Path(directory) / "export"
            bgm.export(song, stems, dest)
            restored = bgm.load_song(dest / "song.json")
            np.testing.assert_array_equal(stems["melody"], bgm.render_part(restored, "melody"))
            sources = json.loads((dest / "sources.json").read_text(encoding="utf-8"))
            self.assertEqual(sources["melody_source"]["kind"], "humming")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is optional")
    def test_mp3_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hum.wav"
            wavfile.write(path, 16000, fake_hum())
            target = path.with_suffix(".mp3")
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(path), str(target)], check=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            notes = humming.transcribe(humming.read_audio(target))
            self.assertEqual([n["midi"] for n in notes], [60, 62, 64, 67])

    def test_auto_phrase_original_rhythm_and_long_note(self):
        song = bgm.compose(bars=8)
        song["bpm"] = 120
        detected = [{"start": 0, "end": 1, "midi": 60}, {"start": 1.4, "end": 4, "midi": 64}]
        result, report = humming.apply_melody(song, detected, grid=0)
        self.assertEqual(report["phrase_bars"], 2)
        self.assertAlmostEqual(result["parts"]["melody"]["notes"][1]["beat"], 2.8)
        sustained, _ = humming.apply_melody(song, [{"start": 0, "end": 20, "midi": 60}], phrase_bars=8)
        bgm.validate(sustained)
        self.assertEqual([n["duration"] for n in sustained["parts"]["melody"]["notes"]], [16, 16])
        with self.assertRaises(ValueError): humming.apply_melody(song, detected, phrase_bars=16)

    def test_recorder_limit_and_closure_without_opening_microphone(self):
        import sounddevice as sd
        class FakeStream:
            active = True
            closed = False
            def __init__(self, **kwargs): self.callback = kwargs["callback"]
            def start(self): pass
            def stop(self): self.active = False
            def close(self): self.closed = True
        recorder = humming.MicrophoneRecorder()
        with patch.object(sd, "query_devices", return_value={"default_samplerate": 16000}), patch.object(sd, "InputStream", FakeStream):
            recorder.start()
            stream = recorder.stream
            with self.assertRaises(sd.CallbackStop):
                stream.callback(np.zeros((16000 * 61, 1), dtype=np.float32), 16000 * 61, None, None)
            data, rate = recorder.stop()
            self.assertEqual(len(data), 16000 * 60)
            self.assertEqual(rate, 16000)
            self.assertTrue(stream.closed)
            self.assertIsNone(recorder.stream)


if __name__ == "__main__": unittest.main()

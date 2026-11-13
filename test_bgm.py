import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile
import bgm


class ComposerTests(unittest.TestCase):
    def test_sample_octave_matches_score(self):
        if not bgm.sample_data("xylophone"):
            self.skipTest("Optional CC0 samples are not installed")
        audio = bgm.note_audio("xylophone", 72, .4)
        spectrum = np.abs(np.fft.rfft(audio))
        frequencies = np.fft.rfftfreq(len(audio), 1 / bgm.SR)
        dominant = frequencies[int(np.argmax(spectrum))]
        self.assertLess(abs(dominant - 523.25), 20, "Sample note names use a different octave convention")

    def test_reproducible_and_part_isolation(self):
        song = bgm.compose(seed=42, bars=4)
        first = bgm.render(song)
        second = bgm.render(copy.deepcopy(song))
        for name in bgm.PARTS:
            np.testing.assert_array_equal(first[name], second[name])
        for name in bgm.PARTS:
            changed = copy.deepcopy(song)
            changed["parts"][name]["notes"] = bgm.make_notes(name, 139, 4)
            self.assertNotEqual(changed["parts"][name]["notes"], song["parts"][name]["notes"])
            other = next(p for p in bgm.PARTS if p != name)
            np.testing.assert_array_equal(first[other], bgm.render_part(changed, other))
            self.assertFalse(np.array_equal(first[name], bgm.render_part(changed, name)))

    def test_export_duration_boundary_and_roundtrip(self):
        for preset in bgm.PRESETS:
            song = bgm.compose(preset, bars=4)
            audio = bgm.mix(song, bgm.render(song))
            expected = round(4 * 4 * 60 / song["bpm"] * bgm.SR)
            self.assertEqual(audio.shape, (expected, 2))
            self.assertTrue(np.isfinite(audio).all())
            self.assertLessEqual(float(np.max(np.abs(audio))), .971)
            self.assertGreater(float(np.sqrt(np.mean(audio ** 2))), .005)
            self.assertLess(float(np.max(np.abs(audio[0] - audio[-1]))), .025)
            with tempfile.TemporaryDirectory() as directory:
                stems = bgm.render(song)
                path = bgm.export(song, stems, directory)
                rate, data = wavfile.read(path)
                self.assertEqual(rate, bgm.SR)
                self.assertEqual(len(data), expected)
                self.assertEqual(bgm.load_song(Path(directory) / "song.json"), song)
                self.assertTrue((Path(directory) / "sources.json").exists())

    def test_gain_mute_and_minor_preserve_notes(self):
        song = bgm.compose(bars=4)
        stems = bgm.render(song)
        before = copy.deepcopy(song["parts"]["melody"]["notes"])
        song["parts"]["bass"]["gain"] = 0
        np.testing.assert_array_equal(stems["melody"], bgm.render_part(song, "melody"))
        song["mode"] = "minor"
        self.assertEqual(before, song["parts"]["melody"]["notes"])
        self.assertFalse(np.array_equal(stems["melody"], bgm.render_part(song, "melody")))
        for part in song["parts"].values(): part["muted"] = True
        np.testing.assert_array_equal(bgm.mix(song, stems), np.zeros((len(stems["bass"]), 2)))

    def test_invalid_tempo(self):
        song = bgm.compose()
        song["bpm"] = 0
        with self.assertRaises(ValueError): bgm.render(song)


if __name__ == "__main__":
    unittest.main()

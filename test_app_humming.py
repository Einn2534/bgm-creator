"""UI integration with a fake audio device and synthesized input, no microphone."""
import copy
import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["SDL_AUDIODRIVER"] = "dummy"
from scipy.io import wavfile
import app
import bgm
from humming_ui import HummingDialog
from test_humming import fake_hum


class AppHummingTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = app.App(self.root)
        self.wait_ready(initial=True)

    def tearDown(self):
        self.app.close()

    def wait_ready(self, initial=False):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            self.root.update()
            if not self.app.busy and self.app.stems is not None:
                return
            time.sleep(.015)
        self.fail("UI worker did not finish")

    def test_import_undo_and_source_reset(self):
        before = copy.deepcopy(self.app.song)
        original_stems = dict(self.app.stems)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hum.wav"
            wavfile.write(path, 16000, fake_hum())
            self.app.import_humming(path, phrase_bars=2, grid=.25)
            self.wait_ready()
            self.assertIn("鼻歌を取り込みました", self.app.status.get())
            self.assertEqual(self.app.song["parts"]["melody"]["source"]["kind"], "humming")
            for name in bgm.PARTS:
                if name != "melody": self.assertIs(self.app.stems[name], original_stems[name])
            self.app.undo()
            self.assertEqual(self.app.song, before)
            self.app.undo()
            self.assertEqual(self.app.song["parts"]["melody"]["source"]["kind"], "humming")
            self.app.regenerate("melody")
            self.wait_ready()
            self.assertNotIn("source", self.app.song["parts"]["melody"])

    def test_invalid_input_keeps_song(self):
        before = copy.deepcopy(self.app.song)
        with patch.object(app.messagebox, "showerror") as error:
            self.app.import_humming(Path("does-not-exist.wav"))
            self.wait_ready()
            error.assert_called_once()
        self.assertEqual(self.app.song, before)

    def test_dialog_does_not_open_microphone_and_submits_options(self):
        received = []
        with patch("humming_ui.MicrophoneRecorder") as recorder:
            dialog = HummingDialog(self.root, lambda path, **options: received.append((path, options)), 8, 120)
            self.root.update()
            recorder.assert_not_called()
            self.assertEqual(str(dialog.import_button["state"]), "disabled")
            dialog.path = Path("hum.wav")
            dialog.phrase.set("2小節")
            dialog.pitch.set("曲の調に合わせる")
            dialog.submit()
            self.assertEqual(received[0][1], {"phrase_bars": 2, "grid": .25, "snap_to_key": True})


class PlatformHelpersTests(unittest.TestCase):
    def test_open_in_file_manager_uses_macos_open(self):
        path = Path("/tmp/BGM output")
        with patch.object(app.sys, "platform", "darwin"), patch.object(app.subprocess, "Popen") as popen:
            app.open_in_file_manager(path)
        popen.assert_called_once_with(["open", str(path)])


if __name__ == "__main__": unittest.main()

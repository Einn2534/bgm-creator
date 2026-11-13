"""Fetch a small CC0 subset of VSCO 2 CE, pinned to an upstream commit."""
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

COMMIT = "440300901dfe9275fd84e0b7763af1f8443ae62e"
BASE = f"https://raw.githubusercontent.com/sgossner/VSCO-2-CE/{COMMIT}/"
DEST = Path(__file__).resolve().parent / "assets" / "samples"
FILES = [
    ("xylophone", 72, "Percussion/Xylo/Xylo_Medium_C5_ff_01_far.wav"),
    ("xylophone", 79, "Percussion/Xylo/Xylo_Medium_G5_ff_01_far.wav"),
    ("xylophone", 84, "Percussion/Xylo/Xylo_Medium_C6_ff_01_far.wav"),
    ("marimba", 60, "Percussion/Marimba/Marimba_hit_Outrigger_C4_loud_01.wav"),
    ("marimba", 67, "Percussion/Marimba/Marimba_hit_Outrigger_G4_loud_01.wav"),
    ("marimba", 77, "Percussion/Marimba/Marimba_hit_Outrigger_F5_loud_01.wav"),
    ("glockenspiel", 84, "Percussion/Glock/glock_medium_C6.wav"),
    ("pizzicato", 45, "Strings/Violin Section/Pizz/VlnEns_Pizz_A2_v1_rr1.wav"),
    ("pizzicato", 57, "Strings/Violin Section/Pizz/VlnEns_Pizz_A3_v1_rr1.wav"),
    ("pizzicato", 60, "Strings/Violin Section/Pizz/VlnEns_Pizz_C4_v1_rr1.wav"),
    ("pizzicato", 74, "Strings/Violin Section/Pizz/VlnEns_Pizz_D5_v1_rr1.wav"),
]


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    old_path = DEST / "manifest.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {"samples": []}
    known = {s["file"]: s["sha256"] for s in old["samples"]}
    manifest = {"library": "VSCO 2 Community Edition", "authors": "Sam Gossner & Simon Dalzell; sample cutting: Elan Hickler/Soundemote",
                "license": "CC0-1.0", "source": "https://github.com/sgossner/VSCO-2-CE", "commit": COMMIT, "samples": []}
    for instrument, midi, source in FILES:
        name = f"{instrument}_{midi}.wav"
        # Upstream uses C3 for middle C (MIDI 60); our score uses C4.
        midi += 12
        path = DEST / name
        url = BASE + urllib.parse.quote(source, safe="/")
        if not path.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
                raise ValueError(f"WAVではない応答: {source}")
            digest = hashlib.sha256(data).hexdigest()
            if name in known and digest != known[name]:
                raise ValueError(f"音源のハッシュ不一致: {name}")
            path.write_bytes(data)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if name in known and known[name] != digest:
            raise ValueError(f"音源のハッシュ不一致: {name}")
        manifest["samples"].append({"instrument": instrument, "midi": midi, "file": name, "url": url, "sha256": digest})
        print(name, flush=True)
    with urllib.request.urlopen(BASE + "LICENSE", timeout=60) as response:
        (DEST / "VSCO-LICENSE.txt").write_bytes(response.read())
    old_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CC0 samples ready.")


if __name__ == "__main__":
    main()

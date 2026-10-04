import os
import re
import sys
import math
import wave
import struct
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=1)
except Exception:
    pygame = None

SEMITONES = {
    'C': 0, 'C#': 1, 'DB': 1,
    'D': 2, 'D#': 3, 'EB': 3,
    'E': 4,
    'F': 5, 'F#': 6, 'GB': 6,
    'G': 7, 'G#': 8, 'AB': 8,
    'A': 9, 'A#': 10, 'BB': 10,
    'B': 11
}

def midi_to_freq(midi_num):
    return 440.0 * (2.0 ** ((midi_num - 69) / 12.0))

def parse_note_expression(expr):
    token = expr.strip()
    
    # Check for named triads: Cmaj, Amin, F#maj3, Dmin5
    chord_match = re.match(r'^([A-G][#bB]?)([0-8])?(maj|min|m)$', token, re.I)
    if chord_match:
        root_name = chord_match.group(1).upper()
        octave = int(chord_match.group(2)) if chord_match.group(2) else 4
        flavor = chord_match.group(3).lower()

        if root_name in SEMITONES:
            root_midi = (octave + 1) * 12 + SEMITONES[root_name]
            interval = 4 if flavor == 'maj' else 3
            return [midi_to_freq(root_midi), midi_to_freq(root_midi + interval), midi_to_freq(root_midi + 7)]

    # Check for single notes or stacked polyphony: C3, C4E4G4, CEG
    note_tokens = re.findall(r'([A-G][#bB]?)([0-8])?', token, re.I)
    freqs = []
    for n, oct_str in note_tokens:
        n_up = n.upper()
        if n_up in SEMITONES:
            oct_val = int(oct_str) if oct_str else 4
            midi_val = (oct_val + 1) * 12 + SEMITONES[n_up]
            freqs.append(midi_to_freq(midi_val))

    return freqs

class PTAFApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PTAF Desktop Player")
        self.root.geometry("640x520")
        self.root.configure(bg="#0f141c")

        self.temp_file = None

        nav = tk.Frame(root, bg="#0f141c")
        nav.pack(fill="x", padx=12, pady=10)

        tk.Button(nav, text="Open .PTAF", command=self.open_file, bg="#1e2633", fg="#c9d1d9", relief="flat", padx=10).pack(side="left", padx=4)
        tk.Button(nav, text="▶ Play", command=self.play, bg="#059669", fg="#ffffff", font=("Courier", 10, "bold"), relief="flat", padx=12).pack(side="left", padx=4)
        tk.Button(nav, text="⏹ Stop", command=self.stop, bg="#dc2626", fg="#ffffff", font=("Courier", 10, "bold"), relief="flat", padx=12).pack(side="left", padx=4)
        tk.Button(nav, text="Export .WAV", command=self.export_wav, bg="#2563eb", fg="#ffffff", font=("Courier", 10), relief="flat", padx=10).pack(side="right", padx=4)

        pad = tk.LabelFrame(root, text=" PTAF Generator Pad ", bg="#151b26", fg="#00e5ff", font=("Courier", 9, "bold"), padx=8, pady=6)
        pad.pack(fill="x", padx=12, pady=4)

        presets = [
            ("C3", "note = C3"), ("C4", "note = C4"), ("C5", "note = C5"),
            ("Cmaj", "note = Cmaj"), ("Gmaj", "note = Gmaj"),
            ("Amin", "note = Amin"), ("Dmin", "note = Dmin"),
            ("Pitch 440", "pitch = 440")
        ]
        for label, snippet in presets:
            tk.Button(pad, text=label, command=lambda s=snippet: self.insert_command(s), bg="#212b3b", fg="#e2e8f0", relief="flat", font=("Courier", 8)).pack(side="left", padx=2)

        self.editor = tk.Text(root, bg="#0a0d14", fg="#38bdf8", insertbackground="#ffffff", font=("Courier", 11), relief="flat", padx=10, pady=10)
        self.editor.pack(fill="both", expand=True, padx=12, pady=8)

        default_score = (
            "* PTAF Full Range Showcase\n"
            "^\n"
            "tempo = 90\n"
            "note = C3\n"
            "note = Cmaj\n"
            "note = Amin\n"
            "note = Fmaj\n"
            "note = Gmaj\n"
            "note = C4E4G4C5\n"
            "pitch = 523.25\n"
            "^"
        )
        self.editor.insert(tk.END, default_score)

        self.status = tk.Label(root, text="Ready | Target: Windows 7+, macOS 10.14+, Debian 10+", bg="#0f141c", fg="#64748b", anchor="w", font=("Courier", 9))
        self.status.pack(fill="x", padx=12, pady=6)

    def insert_command(self, cmd):
        text = self.editor.get("1.0", tk.END)
        end_carat = text.rfind("^")
        if end_carat != -1:
            self.editor.delete("1.0", tk.END)
            self.editor.insert(tk.END, text[:end_carat] + cmd + "\n" + text[end_carat:])
        else:
            self.editor.insert(tk.END, "\n" + cmd)

    def open_file(self):
        p = filedialog.askopenfilename(filetypes=[("PTAF Score", "*.PTAF *.ptaf *.txt"), ("All Files", "*.*")])
        if p:
            with open(p, "r", encoding="utf-8") as f:
                self.editor.delete("1.0", tk.END)
                self.editor.insert(tk.END, f.read())
            self.status.config(text="Loaded: " + os.path.basename(p))

    def synthesize(self):
        raw = self.editor.get("1.0", tk.END)
        start = raw.find("^")
        end = raw.rfind("^")
        content = raw[start + 1:end] if (start != -1 and end != -1 and start != end) else raw[start + 1:]
        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("*")]

        tempo = 120.0
        beat_sec = 60.0 / tempo
        samples = []
        sr = 44100

        for line in lines:
            if line.startswith("tempo ="):
                try:
                    tempo = float(line.split("=")[1].strip())
                    beat_sec = 60.0 / tempo
                except ValueError:
                    pass
            elif line.startswith("note =") or line.startswith("pitch ="):
                if line.startswith("note ="):
                    payload = line.split("=")[1].strip()
                    freqs = parse_note_expression(payload)
                else:
                    try:
                        raw_val = line.split("=")[1].strip()
                        freqs = [float(v.strip()) for v in raw_val.split(",") if v.strip()]
                    except ValueError:
                        freqs = []

                if not freqs:
                    continue

                dur = beat_sec * 0.9
                count = int(sr * dur)
                fade = int(sr * 0.02)
                for i in range(count):
                    val = sum(math.sin(2.0 * math.pi * f * (i / sr)) for f in freqs) / max(len(freqs), 1) * 0.35
                    if i > count - fade:
                        val *= (count - i) / fade
                    samples.append(int(val * 32767))
                samples.extend([0] * int(sr * (beat_sec * 0.1)))

        return samples, sr

    def play(self):
        self.stop()
        samples, sr = self.synthesize()
        if not samples:
            return

        tf = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.temp_file = tf.name
        tf.close()

        with wave.open(self.temp_file, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(struct.pack("<{}h".format(len(samples)), *samples))

        if pygame and pygame.mixer.get_init():
            pygame.mixer.music.load(self.temp_file)
            pygame.mixer.music.play()
            self.status.config(text="Playing audio...")
        else:
            self.status.config(text="Rendered WAV: " + self.temp_file)

    def export_wav(self):
        dest = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV Audio", "*.wav")])
        if dest:
            samples, sr = self.synthesize()
            with wave.open(dest, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(struct.pack("<{}h".format(len(samples)), *samples))
            self.status.config(text="Exported: " + os.path.basename(dest))

    def stop(self):
        if pygame and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        self.status.config(text="Stopped")

if __name__ == "__main__":
    root = tk.Tk()
    app = PTAFApp(root)
    root.mainloop()
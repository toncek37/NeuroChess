from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


ROOT = Path(__file__).resolve().parents[2]


class DatasetApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NeuroChess Training Dataset Generator")
        self.geometry("820x650")
        self.minsize(720, 560)
        self.process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        self.stockfish = tk.StringVar()
        self.output = tk.StringVar(value=str(ROOT / "datasets" / "training_10000.jsonl"))
        self.positions = tk.IntVar(value=10000)
        self.depth = tk.IntVar(value=12)
        self.multipv = tk.IntVar(value=8)
        self.seed = tk.IntVar(value=42)
        self.status = tk.StringVar(value="Ready")

        self._build()
        self.after(100, self._poll)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Generate teacher-labelled training data", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Generate legal positions, analyse them with Stockfish, and save one labelled JSONL ready for Training GUI.", wraplength=760).pack(anchor="w", pady=(4, 16))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        self._path_row(form, 0, "Stockfish executable", self.stockfish, self._pick_stockfish)
        self._path_row(form, 1, "Output labelled JSONL", self.output, self._pick_output)

        opts = ttk.LabelFrame(outer, text="Dataset", padding=12)
        opts.pack(fill="x", pady=14)
        ttk.Label(opts, text="Positions").grid(row=0, column=0, sticky="w")
        preset = ttk.Combobox(opts, textvariable=self.positions, values=(1000, 10000, 100000), width=12)
        preset.grid(row=0, column=1, sticky="w", padx=(8, 24))
        ttk.Label(opts, text="Teacher depth").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(opts, from_=4, to=30, textvariable=self.depth, width=8).grid(row=0, column=3, padx=(8, 24))
        ttk.Label(opts, text="MultiPV").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(opts, from_=1, to=32, textvariable=self.multipv, width=8).grid(row=0, column=5, padx=(8, 0))
        ttk.Label(opts, text="Seed").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(opts, textvariable=self.seed, width=14).grid(row=1, column=1, sticky="w", padx=(8, 24), pady=(10, 0))
        ttk.Label(opts, text="Depth 10–12 is good for a first dataset; higher values improve labels but take much longer.", wraplength=500).grid(row=1, column=2, columnspan=4, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        self.start_btn = ttk.Button(buttons, text="Generate training dataset", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        ttk.Label(buttons, textvariable=self.status).pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(12, 8))
        self.log = tk.Text(outer, height=20, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

    def _path_row(self, parent, row, label, variable, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="Browse…", command=command).grid(row=row, column=2, pady=5)
        parent.columnconfigure(1, weight=1)

    def _pick_stockfish(self) -> None:
        path = filedialog.askopenfilename(title="Select Stockfish", filetypes=[("Executables", "*.exe"), ("All files", "*.*")])
        if path:
            self.stockfish.set(path)

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(title="Save labelled dataset", defaultextension=".jsonl", filetypes=[("JSON Lines", "*.jsonl")], initialfile=f"training_{self.positions.get()}.jsonl")
        if path:
            self.output.set(path)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self) -> None:
        engine = Path(self.stockfish.get().strip())
        if not engine.is_file():
            messagebox.showerror("Stockfish", "Select a valid Stockfish executable.")
            return
        try:
            count = int(self.positions.get())
            depth = int(self.depth.get())
            multipv = int(self.multipv.get())
            seed = int(self.seed.get())
        except (ValueError, tk.TclError):
            messagebox.showerror("Settings", "Positions, depth, MultiPV and seed must be integers.")
            return
        if count <= 0 or depth <= 0 or multipv <= 0:
            messagebox.showerror("Settings", "Positions, depth and MultiPV must be positive.")
            return
        output = Path(self.output.get().strip())
        if output.suffix.lower() != ".jsonl":
            output = output.with_suffix(".jsonl")
            self.output.set(str(output))
        output.parent.mkdir(parents=True, exist_ok=True)
        raw = output.with_name(output.stem + "_positions.jsonl")
        games = (count + 3) // 4

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start(10)
        self.status.set("Generating positions…")
        self._append(f"Target: approximately {count} labelled positions")
        self._append(f"Stockfish: {engine}")
        self._append(f"Teacher: depth {depth}, MultiPV {multipv}")

        def worker() -> None:
            try:
                gen = [sys.executable, "-m", "data.generate_positions", "--self-play-games", str(games), "--output", str(raw), "--seed", str(seed), "--positions-per-game", "4", "--min-ply", "12", "--max-ply", "160"]
                rc = self._run(gen, "Generating legal positions")
                if rc != 0:
                    raise RuntimeError("Position generation failed.")
                self.events.put(("status", "Stockfish is labelling positions…"))
                label = [sys.executable, "-m", "data.label_positions", "--input", str(raw), "--output", str(output), "--engine", str(engine), "--depth", str(depth), "--multipv", str(multipv)]
                rc = self._run(label, "Teacher labelling")
                if rc != 0:
                    raise RuntimeError("Teacher labelling failed.")
                try:
                    raw.unlink()
                except OSError:
                    pass
                self.events.put(("done", str(output)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _run(self, command: list[str], label: str) -> int:
        self.events.put(("log", f"--- {label} ---"))
        env = dict(__import__("os").environ)
        env["PYTHONPATH"] = str(ROOT / "python") + __import__("os").pathsep + env.get("PYTHONPATH", "")
        self.process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.events.put(("log", line.rstrip()))
        return self.process.wait()

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            self._append("Stopping current process…")
        self.status.set("Stopping…")

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append(str(value))
                elif kind == "status":
                    self.status.set(str(value))
                elif kind == "done":
                    self._finish()
                    self.status.set("Dataset ready")
                    self._append(f"DONE: {value}")
                    messagebox.showinfo("Dataset ready", f"Training dataset created:\n{value}\n\nSelect this file in run_training_gui.bat.")
                elif kind == "error":
                    self._finish()
                    self.status.set("Failed")
                    self._append(f"ERROR: {value}")
                    messagebox.showerror("Dataset generation failed", str(value))
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self) -> None:
        self.process = None
        self.progress.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")


if __name__ == "__main__":
    DatasetApp().mainloop()

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


RESULT_RE = re.compile(r"Estimated Stockfish-equivalent Elo: ([\d.-]+) \((\d+)% CI ([\d.-]+)\.\.([\d.-]+)\)")
NEURAL_MODES = ("Classical", "Policy", "Value", "Policy + Value")
SETTINGS_PATH = Path(".neurochess_benchmark_gui.json")


def _load_settings() -> dict[str, str]:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_settings(data: dict[str, str]) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _default_engine() -> str:
    candidates = [
        Path("build-neural/neurochess.exe"),
        Path("build/neurochess.exe"),
        Path("build/Release/neurochess.exe"),
        Path("build/Debug/neurochess.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return ""


def _default_model() -> str:
    candidates = sorted(Path("models").glob("**/*.onnx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0].resolve()) if candidates else ""


class BenchmarkApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NeuroChess Elo Benchmark")
        self.geometry("940x760")
        self.minsize(800, 620)
        self.proc: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple[str, str | int | None]] = queue.Queue()

        saved = _load_settings()
        self.engine_var = tk.StringVar(value=saved.get("engine", _default_engine()))
        self.stockfish_var = tk.StringVar(value=saved.get("stockfish", ""))
        self.neural_model_var = tk.StringVar(value=saved.get("neural_model", _default_model()))
        self.neural_mode_var = tk.StringVar(value="Classical")
        self.neural_blend_var = tk.IntVar(value=50)
        self.movetime_var = tk.IntVar(value=100)
        self.probe_var = tk.IntVar(value=8)
        self.refine_var = tk.IntVar(value=24)
        self.concurrency_var = tk.IntVar(value=max(1, min(4, os.cpu_count() or 1)))
        self.seed_var = tk.IntVar(value=1)
        self.output_var = tk.StringVar(value=saved.get("output", str(Path("elo-ladder-results").resolve())))
        self.status_var = tk.StringVar(value="Ready")
        self.elo_var = tk.StringVar(value="—")
        self.ci_var = tk.StringVar(value="—")
        self.games_var = tk.StringVar(value="—")

        self._build_ui()
        self.after(100, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(8, weight=1)

        ttk.Label(root, text="NeuroChess engine").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.engine_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Browse…", command=lambda: self._browse_exe(self.engine_var)).grid(row=0, column=2)

        ttk.Label(root, text="Stockfish engine").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.stockfish_var).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Browse…", command=lambda: self._browse_exe(self.stockfish_var)).grid(row=1, column=2)

        neural = ttk.LabelFrame(root, text="Neural ablation", padding=10)
        neural.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        neural.columnconfigure(1, weight=1)
        ttk.Label(neural, text="ONNX model").grid(row=0, column=0, sticky="w")
        ttk.Entry(neural, textvariable=self.neural_model_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(neural, text="Browse…", command=self._browse_model).grid(row=0, column=2)
        ttk.Label(neural, text="Mode").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(neural, textvariable=self.neural_mode_var, values=NEURAL_MODES, state="readonly", width=18).grid(
            row=1, column=1, sticky="w", padx=8, pady=(8, 0)
        )
        ttk.Label(neural, text="Value blend %").grid(row=1, column=1, sticky="e", padx=(0, 110), pady=(8, 0))
        ttk.Spinbox(neural, textvariable=self.neural_blend_var, from_=0, to=100, width=7).grid(
            row=1, column=2, sticky="w", pady=(8, 0)
        )

        settings = ttk.LabelFrame(root, text="Test settings", padding=10)
        settings.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 6))
        for i in range(5):
            settings.columnconfigure(i, weight=1)

        self._spin(settings, "Move time [ms]", self.movetime_var, 10, 5000, 0)
        self._spin(settings, "Probe games", self.probe_var, 2, 200, 1, increment=2)
        self._spin(settings, "Refine games", self.refine_var, 2, 1000, 2, increment=2)
        self._spin(settings, "Parallel games", self.concurrency_var, 1, 32, 3)
        self._spin(settings, "Seed", self.seed_var, 0, 1_000_000, 4)

        output = ttk.Frame(root)
        output.grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)
        output.columnconfigure(1, weight=1)
        ttk.Label(output, text="Results folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(output, textvariable=self.output_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(output, text="Browse…", command=self._browse_output).grid(row=0, column=2)

        controls = ttk.Frame(root)
        controls.grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
        self.start_btn = ttk.Button(controls, text="Start Elo test", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        ttk.Label(controls, textvariable=self.status_var).pack(side="left", padx=12)

        summary = ttk.LabelFrame(root, text="Result", padding=10)
        summary.grid(row=6, column=0, columnspan=3, sticky="ew", pady=6)
        for i in range(6):
            summary.columnconfigure(i, weight=1)
        ttk.Label(summary, text="Estimated Elo").grid(row=0, column=0)
        ttk.Label(summary, textvariable=self.elo_var, font=("Segoe UI", 16, "bold")).grid(row=1, column=0)
        ttk.Label(summary, text="95% CI").grid(row=0, column=2)
        ttk.Label(summary, textvariable=self.ci_var, font=("Segoe UI", 12)).grid(row=1, column=2)
        ttk.Label(summary, text="Games").grid(row=0, column=4)
        ttk.Label(summary, textvariable=self.games_var, font=("Segoe UI", 12)).grid(row=1, column=4)

        ttk.Label(
            root,
            text="For a clean comparison keep move time, game counts and seed unchanged between Classical / Policy / Value modes.",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 0))

        log_frame = ttk.LabelFrame(root, text="Progress", padding=6)
        log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled", height=14)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    @staticmethod
    def _spin(parent: ttk.Widget, label: str, variable: tk.Variable, lo: int, hi: int, col: int, increment: int = 1) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=col, padx=6, sticky="ew")
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Spinbox(frame, textvariable=variable, from_=lo, to=hi, increment=increment, width=10).pack(fill="x")

    def _browse_exe(self, variable: tk.StringVar) -> None:
        path = filedialog.askopenfilename(title="Select engine executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if path:
            variable.set(path)
            self._save_preferences()

    def _browse_model(self) -> None:
        path = filedialog.askopenfilename(title="Select NeuroChess ONNX model", filetypes=[("ONNX model", "*.onnx"), ("All files", "*.*")])
        if path:
            self.neural_model_var.set(path)
            self._save_preferences()

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select results folder")
        if path:
            self.output_var.set(path)
            self._save_preferences()

    def _save_preferences(self) -> None:
        _save_settings({
            "engine": self.engine_var.get().strip(),
            "stockfish": self.stockfish_var.get().strip(),
            "neural_model": self.neural_model_var.get().strip(),
            "output": self.output_var.get().strip(),
        })

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _validate(self) -> tuple[Path, Path, Path | None] | None:
        engine = Path(self.engine_var.get().strip())
        stockfish = Path(self.stockfish_var.get().strip())
        if not engine.is_file():
            messagebox.showerror("NeuroChess Elo Benchmark", "Select a valid NeuroChess executable.")
            return None
        if not stockfish.is_file():
            messagebox.showerror("NeuroChess Elo Benchmark", "Select a valid Stockfish executable.")
            return None
        if self.probe_var.get() % 2 or self.refine_var.get() % 2:
            messagebox.showerror("NeuroChess Elo Benchmark", "Probe and refine game counts must be even (color-paired games).")
            return None
        mode = self.neural_mode_var.get()
        model: Path | None = None
        if mode != "Classical":
            model = Path(self.neural_model_var.get().strip())
            if not model.is_file():
                messagebox.showerror("NeuroChess Elo Benchmark", "Neural modes require a valid .onnx model.")
                return None
        return engine, stockfish, model

    def _start(self) -> None:
        validated = self._validate()
        if validated is None:
            return
        engine, stockfish, model = validated
        output = Path(self.output_var.get().strip())
        output.mkdir(parents=True, exist_ok=True)
        self._save_preferences()
        self.elo_var.set("—")
        self.ci_var.set("—")
        self.games_var.set("—")
        self.status_var.set("Running…")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        mode = self.neural_mode_var.get()
        self._append(f"Starting adaptive Stockfish Elo ladder — mode: {mode}")
        self._append("Benchmark parameters:")
        self._append(f"  NeuroChess: {engine}")
        self._append(f"  Stockfish: {stockfish}")
        self._append(f"  Mode: {mode}")
        if mode != "Classical" and model is not None:
            self._append(f"  ONNX model: {model}")
            self._append(f"  Value blend: {self.neural_blend_var.get()}%")
        self._append(f"  Move time: {self.movetime_var.get()} ms/move")
        self._append(f"  Probe games: {self.probe_var.get()}")
        self._append(f"  Refine games: {self.refine_var.get()}")
        self._append(f"  Parallel games: {self.concurrency_var.get()}")
        self._append(f"  Seed: {self.seed_var.get()}")
        self._append(f"  Results folder: {output}")
        self._append("----------------------------------------")

        cmd = [
            sys.executable, "-u", "-m", "match_runner.ladder_cli",
            "--engine", str(engine),
            "--stockfish", str(stockfish),
            "--probe-games", str(self.probe_var.get()),
            "--refine-games", str(self.refine_var.get()),
            "--movetime-ms", str(self.movetime_var.get()),
            "--concurrency", str(self.concurrency_var.get()),
            "--seed", str(self.seed_var.get()),
            "--output-dir", str(output),
        ]
        if mode != "Classical" and model is not None:
            policy = mode in ("Policy", "Policy + Value")
            value = mode in ("Value", "Policy + Value")
            cmd += [
                "--engine-option", f"Neural Model={model}",
                "--engine-option", f"Neural Policy={'true' if policy else 'false'}",
                "--engine-option", f"Neural Value={'true' if value else 'false'}",
                "--engine-option", f"Neural Value Blend={self.neural_blend_var.get()}",
            ]

        env = os.environ.copy()
        python_dir = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = python_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).resolve().parents[2]),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            self.events.put(("line", line.rstrip()))
        code = self.proc.wait()
        self.events.put(("done", code))

    def _stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.status_var.set("Stopping…")
            self._append("Stop requested. Terminating benchmark process…")
            self.proc.terminate()

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "line":
                    line = str(payload)
                    self._append(line)
                    match = RESULT_RE.search(line)
                    if match:
                        self.elo_var.set(match.group(1))
                        self.ci_var.set(f"{match.group(3)} – {match.group(4)}")
                    if line.startswith("Games:"):
                        self.games_var.set(line.split(":", 1)[1].strip())
                elif kind == "done":
                    code = int(payload or 0)
                    self.proc = None
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    if code == 0:
                        self.status_var.set("Completed")
                    else:
                        self.status_var.set("Stopped" if code < 0 else f"Failed ({code})")
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _on_close(self) -> None:
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("NeuroChess Elo Benchmark", "A benchmark is running. Stop it and close?"):
                return
            self.proc.terminate()
        self._save_preferences()
        self.destroy()


def main() -> int:
    BenchmarkApp().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

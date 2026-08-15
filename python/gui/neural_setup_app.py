from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


ROOT = Path(__file__).resolve().parents[2]
ORT_VERSION = "1.29.0"
ORT_URL = f"https://github.com/microsoft/onnxruntime/releases/download/v{ORT_VERSION}/onnxruntime-win-x64-{ORT_VERSION}.zip"


class NeuralSetupApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NeuroChess Neural Engine Setup")
        self.geometry("860x650")
        self.minsize(740, 560)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.proc: subprocess.Popen[str] | None = None

        self.checkpoint = tk.StringVar(value=self._find_checkpoint())
        self.onnx_output = tk.StringVar(value=str(ROOT / "models" / "neurochess.onnx"))
        self.status = tk.StringVar(value="Ready")
        self._build_ui()
        self.after(100, self._poll)

    @staticmethod
    def _find_checkpoint() -> str:
        candidates = sorted(ROOT.glob("models/**/best.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
        return str(candidates[0]) if candidates else ""

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Prepare NeuroChess neural engine", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text=("This exports your trained best.pt to ONNX, downloads the official ONNX Runtime CPU package, "
                  "and builds a separate neural-enabled neurochess.exe. The normal classical build remains untouched."),
            wraplength=800,
        ).pack(anchor="w", pady=(4, 16))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Training checkpoint").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.checkpoint).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(form, text="Browse…", command=self._pick_checkpoint).grid(row=0, column=2)
        ttk.Label(form, text="ONNX model output").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.onnx_output).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(form, text="Browse…", command=self._pick_onnx).grid(row=1, column=2)

        info = ttk.LabelFrame(outer, text="Runtime", padding=10)
        info.pack(fill="x", pady=12)
        ttk.Label(info, text=f"ONNX Runtime {ORT_VERSION} • Windows x64 CPU • installed locally under third_party/").pack(anchor="w")
        ttk.Label(info, text="No system-wide installation is required. The runtime DLL is copied next to the neural engine.").pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill="x")
        self.start_btn = ttk.Button(controls, text="Export model and build neural engine", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        ttk.Label(controls, textvariable=self.status).pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(12, 8))
        self.log = tk.Text(outer, state="disabled", wrap="word", height=22)
        self.log.pack(fill="both", expand=True)

    def _pick_checkpoint(self) -> None:
        path = filedialog.askopenfilename(title="Select best.pt", filetypes=[("PyTorch checkpoint", "*.pt"), ("All files", "*.*")])
        if path:
            self.checkpoint.set(path)
            if not self.onnx_output.get().strip():
                self.onnx_output.set(str(Path(path).with_suffix(".onnx")))

    def _pick_onnx(self) -> None:
        path = filedialog.asksaveasfilename(title="Save ONNX model", defaultextension=".onnx", filetypes=[("ONNX", "*.onnx")])
        if path:
            self.onnx_output.set(path)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self) -> None:
        checkpoint = Path(self.checkpoint.get().strip())
        if not checkpoint.is_file():
            messagebox.showerror("NeuroChess", "Select a valid best.pt checkpoint.")
            return
        output = Path(self.onnx_output.get().strip())
        if output.suffix.lower() != ".onnx":
            output = output.with_suffix(".onnx")
            self.onnx_output.set(str(output))
        output.parent.mkdir(parents=True, exist_ok=True)

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start(10)
        self.status.set("Working…")
        self._append(f"Checkpoint: {checkpoint}")
        self._append(f"ONNX output: {output}")
        threading.Thread(target=self._worker, args=(checkpoint, output), daemon=True).start()

    def _worker(self, checkpoint: Path, output: Path) -> None:
        try:
            runtime_root = self._ensure_runtime()
            self.events.put(("log", "Exporting PyTorch checkpoint to ONNX…"))
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "python") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            export = [sys.executable, "-u", "-m", "training.export_onnx", "--checkpoint", str(checkpoint), "--output", str(output)]
            if self._run(export, env=env) != 0:
                raise RuntimeError("ONNX export failed.")

            self.events.put(("log", "Building C++ engine with ONNX Runtime…"))
            build = ["cmd", "/c", str(ROOT / "build_neural_engine.bat"), str(runtime_root)]
            if self._run(build, env=os.environ.copy()) != 0:
                raise RuntimeError("Neural C++ build failed.")

            engine = ROOT / "build-neural" / "neurochess.exe"
            if not engine.is_file():
                raise RuntimeError("Build finished but build-neural/neurochess.exe is missing.")
            self.events.put(("done", (str(engine), str(output))))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _ensure_runtime(self) -> Path:
        third_party = ROOT / "third_party"
        root = third_party / f"onnxruntime-win-x64-{ORT_VERSION}"
        header = root / "include" / "onnxruntime_cxx_api.h"
        if header.is_file():
            self.events.put(("log", f"ONNX Runtime {ORT_VERSION} already present."))
            return root

        third_party.mkdir(parents=True, exist_ok=True)
        archive = third_party / f"onnxruntime-win-x64-{ORT_VERSION}.zip"
        self.events.put(("status", "Downloading ONNX Runtime…"))
        self.events.put(("log", f"Downloading {ORT_URL}"))
        urllib.request.urlretrieve(ORT_URL, archive)
        self.events.put(("log", "Extracting ONNX Runtime…"))
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(third_party)
        try:
            archive.unlink()
        except OSError:
            pass
        if not header.is_file():
            raise RuntimeError("Downloaded ONNX Runtime package does not contain expected headers.")
        return root

    def _run(self, cmd: list[str], env: dict[str, str]) -> int:
        self.proc = subprocess.Popen(
            cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.events.put(("log", line.rstrip()))
        return self.proc.wait()

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
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
                    engine, model = value  # type: ignore[misc]
                    self._finish()
                    self.status.set("Ready")
                    self._append(f"DONE: neural engine = {engine}")
                    self._append(f"DONE: neural model  = {model}")
                    messagebox.showinfo(
                        "Neural engine ready",
                        f"Engine:\n{engine}\n\nModel:\n{model}\n\nUse these in the Elo benchmark GUI for neural tests.",
                    )
                elif kind == "error":
                    self._finish()
                    self.status.set("Failed")
                    self._append(f"ERROR: {value}")
                    messagebox.showerror("Neural setup failed", str(value))
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self) -> None:
        self.proc = None
        self.progress.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")


if __name__ == "__main__":
    NeuralSetupApp().mainloop()

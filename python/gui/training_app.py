from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

EPOCH_RE = re.compile(r"Epoch\s+(\d+)/\d+: train ([\d.]+) \| val ([\d.]+) \| policy top1 ([\d.]+)%")


class TrainingApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NeuroChess Neural Training")
        self.geometry("880x650")
        self.minsize(760, 540)
        self.proc: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        self.dataset_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path("models/prompt14").resolve()))
        self.epochs_var = tk.IntVar(value=10)
        self.batch_var = tk.IntVar(value=64)
        self.channels_var = tk.IntVar(value=64)
        self.blocks_var = tk.IntVar(value=4)
        self.lr_var = tk.DoubleVar(value=0.001)
        self.status_var = tk.StringVar(value="Ready")
        self.epoch_var = tk.StringVar(value="—")
        self.train_loss_var = tk.StringVar(value="—")
        self.val_loss_var = tk.StringVar(value="—")
        self.top1_var = tk.StringVar(value="—")

        self._build_ui()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(6, weight=1)

        ttk.Label(root, text="Labelled dataset (.jsonl)").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.dataset_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Browse…", command=self._browse_dataset).grid(row=0, column=2)

        ttk.Label(root, text="Model output folder").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Browse…", command=self._browse_output).grid(row=1, column=2)

        settings = ttk.LabelFrame(root, text="Training settings", padding=10)
        settings.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        for i in range(5):
            settings.columnconfigure(i, weight=1)
        self._spin(settings, "Epochs", self.epochs_var, 1, 10000, 0)
        self._spin(settings, "Batch size", self.batch_var, 1, 2048, 1)
        self._spin(settings, "Channels", self.channels_var, 8, 512, 2, 8)
        self._spin(settings, "Residual blocks", self.blocks_var, 1, 32, 3)
        lr_frame = ttk.Frame(settings)
        lr_frame.grid(row=0, column=4, padx=6, sticky="ew")
        ttk.Label(lr_frame, text="Learning rate").pack(anchor="w")
        ttk.Entry(lr_frame, textvariable=self.lr_var, width=10).pack(fill="x")

        controls = ttk.Frame(root)
        controls.grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)
        self.start_btn = ttk.Button(controls, text="Start training", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="Stop", state="disabled", command=self._stop)
        self.stop_btn.pack(side="left", padx=8)
        ttk.Label(controls, textvariable=self.status_var).pack(side="left", padx=12)

        summary = ttk.LabelFrame(root, text="Current metrics", padding=10)
        summary.grid(row=4, column=0, columnspan=3, sticky="ew", pady=6)
        values = [
            ("Epoch", self.epoch_var),
            ("Train loss", self.train_loss_var),
            ("Validation loss", self.val_loss_var),
            ("Policy top-1", self.top1_var),
        ]
        for col, (label, var) in enumerate(values):
            summary.columnconfigure(col, weight=1)
            ttk.Label(summary, text=label).grid(row=0, column=col)
            ttk.Label(summary, textvariable=var, font=("Segoe UI", 12, "bold")).grid(row=1, column=col)

        ttk.Label(root, text="The best validation checkpoint is saved as best.pt.").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

        log_frame = ttk.LabelFrame(root, text="Training log", padding=6)
        log_frame.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    @staticmethod
    def _spin(parent, label, variable, lo, hi, col, increment=1) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=col, padx=6, sticky="ew")
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Spinbox(frame, textvariable=variable, from_=lo, to=hi, increment=increment).pack(fill="x")

    def _browse_dataset(self) -> None:
        path = filedialog.askopenfilename(title="Select labelled JSONL", filetypes=[("JSONL", "*.jsonl"), ("All files", "*.*")])
        if path:
            self.dataset_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select model output folder")
        if path:
            self.output_var.set(path)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self) -> None:
        dataset = Path(self.dataset_var.get().strip())
        if not dataset.is_file():
            messagebox.showerror("NeuroChess Neural Training", "Select a valid labelled JSONL dataset.")
            return
        output = Path(self.output_var.get().strip())
        output.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, "-u", "-m", "training.train",
            "--dataset", str(dataset),
            "--output-dir", str(output),
            "--epochs", str(self.epochs_var.get()),
            "--batch-size", str(self.batch_var.get()),
            "--channels", str(self.channels_var.get()),
            "--blocks", str(self.blocks_var.get()),
            "--learning-rate", str(self.lr_var.get()),
        ]
        env = os.environ.copy()
        python_dir = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = python_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        self.proc = subprocess.Popen(
            cmd, cwd=str(Path(__file__).resolve().parents[2]), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self.status_var.set("Running…")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            self.events.put(("line", line.rstrip()))
        self.events.put(("done", self.proc.wait()))

    def _stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.status_var.set("Stopping…")
            self.proc.terminate()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "line":
                    line = str(payload)
                    self._append(line)
                    m = EPOCH_RE.search(line)
                    if m:
                        self.epoch_var.set(m.group(1))
                        self.train_loss_var.set(m.group(2))
                        self.val_loss_var.set(m.group(3))
                        self.top1_var.set(m.group(4) + "%")
                else:
                    code = int(payload)
                    self.proc = None
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.status_var.set("Completed" if code == 0 else f"Failed ({code})")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _close(self) -> None:
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("NeuroChess Neural Training", "Training is running. Stop it and close?"):
                return
            self.proc.terminate()
        self.destroy()


def main() -> int:
    TrainingApp().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

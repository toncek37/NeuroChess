from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from training.value_debugger import run_value_debug, save_report


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".neurochess_value_debugger.json"


def load_settings() -> dict[str, str]:
    try:
        value = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def save_settings(data: dict[str, str]) -> None:
    try:
        SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


class ValueDebuggerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NeuroChess Value Debugger")
        self.geometry("920x720")
        self.minsize(780, 600)
        saved = load_settings()
        self.model = tk.StringVar(value=saved.get("model", ""))
        self.dataset = tk.StringVar(value=saved.get("dataset", ""))
        self.samples = tk.IntVar(value=int(saved.get("samples", "2000")))
        self.output = tk.StringVar(value=saved.get("output", str(ROOT / "value-debug-results" / "value-report.json")))
        self.status = tk.StringVar(value="Ready")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build()
        self.after(100, self._poll)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(7, weight=1)
        ttk.Label(root, text="Neural Value Debugger", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(root, text="Compares ONNX WDL/value against teacher-labelled positions and runs synthetic extrapolation checks.").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))
        self._path_row(root, 2, "ONNX model", self.model, self._pick_model)
        self._path_row(root, 3, "Labelled dataset", self.dataset, self._pick_dataset)
        self._path_row(root, 4, "Report JSON", self.output, self._pick_output)
        opts = ttk.Frame(root); opts.grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(opts, text="Validation positions").pack(side="left")
        ttk.Spinbox(opts, textvariable=self.samples, from_=100, to=100000, increment=100, width=10).pack(side="left", padx=8)
        self.start_btn = ttk.Button(opts, text="Run value diagnostics", command=self._start); self.start_btn.pack(side="left", padx=(12, 0))
        ttk.Label(opts, textvariable=self.status).pack(side="right")
        self.summary = ttk.Label(root, text="", font=("Segoe UI", 11, "bold"), wraplength=860)
        self.summary.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 8))
        frame = ttk.LabelFrame(root, text="Diagnostic log", padding=6); frame.grid(row=7, column=0, columnspan=3, sticky="nsew"); frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        self.log = tk.Text(frame, state="disabled", wrap="word"); self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, command=self.log.yview); sb.grid(row=0, column=1, sticky="ns"); self.log.configure(yscrollcommand=sb.set)

    def _path_row(self, parent, row, text, var, cmd):
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(parent, text="Browse…", command=cmd).grid(row=row, column=2, pady=4)

    def _pick_model(self):
        p=filedialog.askopenfilename(filetypes=[("ONNX model","*.onnx"),("All files","*.*")]);
        if p: self.model.set(p); self._save()
    def _pick_dataset(self):
        p=filedialog.askopenfilename(filetypes=[("JSON Lines","*.jsonl"),("All files","*.*")]);
        if p: self.dataset.set(p); self._save()
    def _pick_output(self):
        p=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")]);
        if p: self.output.set(p); self._save()
    def _save(self):
        save_settings({"model":self.model.get(),"dataset":self.dataset.get(),"samples":str(self.samples.get()),"output":self.output.get()})
    def _append(self, text):
        self.log.configure(state="normal"); self.log.insert("end", str(text)+"\n"); self.log.see("end"); self.log.configure(state="disabled")

    def _start(self):
        model=Path(self.model.get().strip()); data=Path(self.dataset.get().strip())
        if not model.is_file(): messagebox.showerror("Value Debugger","Select a valid ONNX model."); return
        if not data.is_file(): messagebox.showerror("Value Debugger","Select a valid labelled JSONL dataset."); return
        self._save(); self.start_btn.configure(state="disabled"); self.status.set("Running…"); self.summary.configure(text="")
        def worker():
            try:
                report=run_value_debug(model,data,max_samples=self.samples.get(),progress=lambda m:self.events.put(("log",m)))
                save_report(report,self.output.get())
                self.events.put(("done",report))
            except Exception as exc:
                self.events.put(("error",str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind,val=self.events.get_nowait()
                if kind=="log": self._append(val)
                elif kind=="error":
                    self.start_btn.configure(state="normal"); self.status.set("Failed"); messagebox.showerror("Value Debugger",str(val))
                elif kind=="done":
                    r=val; self.start_btn.configure(state="normal"); self.status.set("Completed")
                    m=r.metrics
                    text=(
                        f"WDL corr {m.pearson_wdl_score:.3f} | clipped-cp corr {m.pearson_cp:.3f} | "
                        f"MAE {m.mae_cp_clipped:.0f} cp | sign {m.sign_agreement_percent:.1f}% "
                        f"(W {m.white_to_move_sign_agreement:.1f}% / B {m.black_to_move_sign_agreement:.1f}%)\n"
                        f"{r.recommendation}"
                    )
                    self.summary.configure(text=text)
                    self._append(f"Report saved: {self.output.get()}")
        except queue.Empty:
            pass
        self.after(100,self._poll)


if __name__ == "__main__":
    ValueDebuggerApp().mainloop()

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Module:
    title: str
    launcher: str
    description: str


MODULES = (
    Module(
        "Play NeuroChess",
        "build_and_play.bat",
        "Build the classical engine if needed and open the playable chess GUI.",
    ),
    Module(
        "Elo Benchmark",
        "run_elo_gui.bat",
        "Measure NeuroChess strength against Stockfish and compare Classical / Policy / Value modes.",
    ),
    Module(
        "Value Debugger",
        "run_value_debugger_gui.bat",
        "Validate ONNX WDL/value against teacher-labelled positions and diagnose orientation/calibration problems.",
    ),
    Module(
        "Dataset Generator",
        "run_dataset_gui.bat",
        "Generate legal chess positions and label them with Stockfish for neural training.",
    ),
    Module(
        "Training",
        "run_training_gui.bat",
        "Train the policy/WDL neural network from a labelled JSONL dataset.",
    ),
    Module(
        "Neural Setup",
        "run_neural_setup_gui.bat",
        "Export a trained checkpoint to ONNX and build the neural-enabled C++ engine.",
    ),
)


class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NeuroChess Launcher")
        self.geometry("760x540")
        self.minsize(660, 470)
        self._status = tk.StringVar(value="Ready")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="NeuroChess", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Development launcher — choose the module you want to run.",
        ).pack(anchor="w", pady=(2, 16))

        modules = ttk.Frame(outer)
        modules.pack(fill="both", expand=True)
        modules.columnconfigure(0, weight=0)
        modules.columnconfigure(1, weight=1)

        for row, module in enumerate(MODULES):
            path = ROOT / module.launcher
            button = ttk.Button(
                modules,
                text=module.title,
                width=22,
                command=lambda m=module: self._launch(m),
            )
            button.grid(row=row, column=0, sticky="ew", padx=(0, 14), pady=7)
            if not path.is_file():
                button.configure(state="disabled")

            description = module.description
            if not path.is_file():
                description += f"  [Missing: {module.launcher}]"
            ttk.Label(modules, text=description, wraplength=460).grid(
                row=row, column=1, sticky="w", pady=7
            )

        ttk.Separator(outer).pack(fill="x", pady=(12, 10))
        footer = ttk.Frame(outer)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self._status).pack(side="left")
        ttk.Button(footer, text="Open project folder", command=self._open_folder).pack(side="right")

    def _launch(self, module: Module) -> None:
        path = ROOT / module.launcher
        if not path.is_file():
            messagebox.showerror("NeuroChess Launcher", f"Launcher not found:\n{path}")
            return

        try:
            if os.name == "nt":
                subprocess.Popen(
                    ["cmd.exe", "/c", str(path)],
                    cwd=ROOT,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen([str(path)], cwd=ROOT)
            self._status.set(f"Started: {module.title}")
        except OSError as exc:
            self._status.set("Launch failed")
            messagebox.showerror("NeuroChess Launcher", f"Could not start {module.title}:\n{exc}")

    def _open_folder(self) -> None:
        try:
            if os.name == "nt":
                os.startfile(ROOT)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(ROOT)])
        except OSError as exc:
            messagebox.showerror("NeuroChess Launcher", f"Could not open project folder:\n{exc}")


if __name__ == "__main__":
    LauncherApp().mainloop()

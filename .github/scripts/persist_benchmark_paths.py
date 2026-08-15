from pathlib import Path

p = Path('python/gui/benchmark_app.py')
text = p.read_text(encoding='utf-8')

text = text.replace('import os\nimport queue', 'import json\nimport os\nimport queue')
text = text.replace('NEURAL_MODES = ("Classical", "Policy", "Value", "Policy + Value")\n', 'NEURAL_MODES = ("Classical", "Policy", "Value", "Policy + Value")\nSETTINGS_PATH = Path(".neurochess_benchmark_gui.json")\n\n\ndef _load_settings() -> dict[str, str]:\n    try:\n        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))\n        return data if isinstance(data, dict) else {}\n    except (OSError, json.JSONDecodeError):\n        return {}\n\n\ndef _save_settings(data: dict[str, str]) -> None:\n    try:\n        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")\n    except OSError:\n        pass\n')

old = '''        self.engine_var = tk.StringVar(value=_default_engine())\n        self.stockfish_var = tk.StringVar()\n        self.neural_model_var = tk.StringVar(value=_default_model())\n'''
new = '''        saved = _load_settings()\n        self.engine_var = tk.StringVar(value=saved.get("engine", _default_engine()))\n        self.stockfish_var = tk.StringVar(value=saved.get("stockfish", ""))\n        self.neural_model_var = tk.StringVar(value=saved.get("neural_model", _default_model()))\n'''
text = text.replace(old, new)
text = text.replace('self.output_var = tk.StringVar(value=str(Path("elo-ladder-results").resolve()))', 'self.output_var = tk.StringVar(value=saved.get("output", str(Path("elo-ladder-results").resolve())))')

text = text.replace('''    def _browse_exe(self, variable: tk.StringVar) -> None:\n        path = filedialog.askopenfilename(title="Select engine executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])\n        if path:\n            variable.set(path)\n''', '''    def _browse_exe(self, variable: tk.StringVar) -> None:\n        path = filedialog.askopenfilename(title="Select engine executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])\n        if path:\n            variable.set(path)\n            self._save_preferences()\n''')
text = text.replace('''        if path:\n            self.neural_model_var.set(path)\n\n    def _browse_output''', '''        if path:\n            self.neural_model_var.set(path)\n            self._save_preferences()\n\n    def _browse_output''')
text = text.replace('''        if path:\n            self.output_var.set(path)\n\n    def _append''', '''        if path:\n            self.output_var.set(path)\n            self._save_preferences()\n\n    def _save_preferences(self) -> None:\n        _save_settings({\n            "engine": self.engine_var.get().strip(),\n            "stockfish": self.stockfish_var.get().strip(),\n            "neural_model": self.neural_model_var.get().strip(),\n            "output": self.output_var.get().strip(),\n        })\n\n    def _append''')
text = text.replace('''        output = Path(self.output_var.get().strip())\n        output.mkdir(parents=True, exist_ok=True)\n''', '''        output = Path(self.output_var.get().strip())\n        output.mkdir(parents=True, exist_ok=True)\n        self._save_preferences()\n''')
text = text.replace('''        self.destroy()\n\n\ndef main()''', '''        self._save_preferences()\n        self.destroy()\n\n\ndef main()''')

p.write_text(text, encoding='utf-8')

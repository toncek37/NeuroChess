from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".neurochess_dataset_gui.json"


def load_settings():
    try: return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception: return {}


class DatasetApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__(); self.title("NeuroChess Training Dataset Generator"); self.geometry("850x680"); self.minsize(740,580)
        self.process=None; self.events=queue.Queue(); saved=load_settings()
        self.stockfish=tk.StringVar(value=saved.get("stockfish","")); self.output=tk.StringVar(value=saved.get("output",str(ROOT/"datasets"/"training_balanced_10000.jsonl")))
        self.positions=tk.IntVar(value=10000); self.depth=tk.IntVar(value=12); self.multipv=tk.IntVar(value=8); self.seed=tk.IntVar(value=42); self.random_top=tk.IntVar(value=3); self.status=tk.StringVar(value="Ready")
        self._build(); self.after(100,self._poll)

    def _build(self):
        outer=ttk.Frame(self,padding=16); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="Balanced Stockfish self-play dataset",font=("Segoe UI",16,"bold")).pack(anchor="w")
        ttk.Label(outer,text="Recommended Value Dataset v2: Stockfish-guided games with an approximately 1/3 losing, 1/3 equal and 1/3 winning teacher-score distribution. No random legal-move self-play.",wraplength=800).pack(anchor="w",pady=(4,16))
        form=ttk.Frame(outer); form.pack(fill="x"); self._path_row(form,0,"Stockfish executable",self.stockfish,self._pick_stockfish); self._path_row(form,1,"Output labelled JSONL",self.output,self._pick_output)
        opts=ttk.LabelFrame(outer,text="Dataset",padding=12); opts.pack(fill="x",pady=14)
        fields=[("Positions",self.positions,1000,2000000),("Teacher depth",self.depth,4,30),("MultiPV",self.multipv,1,32),("Top moves",self.random_top,1,8),("Seed",self.seed,0,1000000)]
        for i,(label,var,lo,hi) in enumerate(fields):
            ttk.Label(opts,text=label).grid(row=0,column=i,sticky="w",padx=5); ttk.Spinbox(opts,textvariable=var,from_=lo,to=hi,width=10).grid(row=1,column=i,sticky="w",padx=5)
        ttk.Label(opts,text="Top moves adds controlled variety: each self-play move is sampled from Stockfish's strongest candidates, weighted by teacher policy.",wraplength=760).grid(row=2,column=0,columnspan=5,sticky="w",pady=(10,0))
        buttons=ttk.Frame(outer); buttons.pack(fill="x"); self.start_btn=ttk.Button(buttons,text="Generate balanced dataset",command=self.start); self.start_btn.pack(side="left"); self.stop_btn=ttk.Button(buttons,text="Stop",command=self.stop,state="disabled"); self.stop_btn.pack(side="left",padx=8); ttk.Label(buttons,textvariable=self.status).pack(side="right")
        self.progress=ttk.Progressbar(outer,mode="indeterminate"); self.progress.pack(fill="x",pady=(12,8)); self.log=tk.Text(outer,height=22,wrap="word",state="disabled"); self.log.pack(fill="both",expand=True)

    def _path_row(self,parent,row,label,var,cmd):
        ttk.Label(parent,text=label).grid(row=row,column=0,sticky="w",pady=5); ttk.Entry(parent,textvariable=var).grid(row=row,column=1,sticky="ew",padx=8,pady=5); ttk.Button(parent,text="Browse…",command=cmd).grid(row=row,column=2); parent.columnconfigure(1,weight=1)
    def _save(self):
        try: SETTINGS.write_text(json.dumps({"stockfish":self.stockfish.get().strip(),"output":self.output.get().strip()},indent=2),encoding="utf-8")
        except OSError: pass
    def _pick_stockfish(self):
        p=filedialog.askopenfilename(title="Select Stockfish",filetypes=[("Executables","*.exe"),("All files","*.*")]);
        if p: self.stockfish.set(p); self._save()
    def _pick_output(self):
        p=filedialog.asksaveasfilename(title="Save balanced labelled dataset",defaultextension=".jsonl",filetypes=[("JSON Lines","*.jsonl")],initialfile=f"training_balanced_{self.positions.get()}.jsonl");
        if p: self.output.set(p); self._save()
    def _append(self,text):
        self.log.configure(state="normal"); self.log.insert("end",text+"\n"); self.log.see("end"); self.log.configure(state="disabled")

    def start(self):
        engine=Path(self.stockfish.get().strip())
        if not engine.is_file(): messagebox.showerror("Stockfish","Select a valid Stockfish executable."); return
        try: count=int(self.positions.get()); depth=int(self.depth.get()); multipv=int(self.multipv.get()); seed=int(self.seed.get()); top=int(self.random_top.get())
        except Exception: messagebox.showerror("Settings","Numeric settings are invalid."); return
        output=Path(self.output.get().strip()); output=output if output.suffix.lower()==".jsonl" else output.with_suffix(".jsonl"); output.parent.mkdir(parents=True,exist_ok=True); self.output.set(str(output)); self._save()
        self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal"); self.progress.start(10); self.status.set("Generating balanced Stockfish self-play…")
        self._append(f"Target: {count} balanced labelled positions"); self._append(f"Stockfish: {engine}"); self._append(f"Teacher: depth {depth}, MultiPV {multipv}, sampled from top {top} moves"); self._append("Target score buckets: ~33% losing / ~33% equal / ~33% winning (threshold ±150 cp)")
        cmd=[sys.executable,"-m","data.balanced_stockfish_dataset","--engine",str(engine),"--output",str(output),"--positions",str(count),"--depth",str(depth),"--multipv",str(multipv),"--seed",str(seed),"--random-top",str(top)]
        threading.Thread(target=self._worker,args=(cmd,output),daemon=True).start()

    def _worker(self,cmd,output):
        try:
            env=dict(__import__('os').environ); env['PYTHONPATH']=str(ROOT/'python')+__import__('os').pathsep+env.get('PYTHONPATH','')
            self.process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            assert self.process.stdout is not None
            for line in self.process.stdout: self.events.put(("log",line.rstrip()))
            rc=self.process.wait()
            if rc: raise RuntimeError(f"Generator exited with code {rc}")
            self.events.put(("done",str(output)))
        except Exception as e: self.events.put(("error",str(e)))
    def stop(self):
        if self.process and self.process.poll() is None: self.process.terminate(); self._append("Stopping…")
    def _poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=="log": self._append(str(value))
                elif kind=="done": self._finish(); self.status.set("Dataset ready"); self._append(f"DONE: {value}"); messagebox.showinfo("Dataset ready",f"Balanced dataset created:\n{value}\n\nTrain a fresh model, export it to ONNX, then run Value Debugger before Elo testing.")
                elif kind=="error": self._finish(); self.status.set("Failed"); self._append(f"ERROR: {value}"); messagebox.showerror("Dataset generation failed",str(value))
        except queue.Empty: pass
        self.after(100,self._poll)
    def _finish(self): self.process=None; self.progress.stop(); self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled")

if __name__=="__main__": DatasetApp().mainloop()

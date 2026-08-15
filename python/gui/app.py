from __future__ import annotations

import argparse
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .uci_client import UciClient, find_default_engine, parse_info_line

PIECES = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}
LIGHT, DARK = "#EEEED2", "#769656"
SELECTED, TARGET, LAST = "#F6F669", "#BACA44", "#CDD26A"
FILES = "abcdefgh"


def parse_fen_board(fen: str) -> tuple[dict[str, str], str]:
    fields = fen.split()
    if len(fields) != 6:
        raise ValueError("Expected six-field FEN")
    board: dict[str, str] = {}
    ranks = fields[0].split("/")
    if len(ranks) != 8:
        raise ValueError("Expected eight ranks")
    for row, data in enumerate(ranks):
        rank = 8 - row
        file_idx = 0
        for ch in data:
            if ch.isdigit():
                file_idx += int(ch)
            else:
                if file_idx >= 8 or ch not in PIECES:
                    raise ValueError("Invalid FEN board")
                board[f"{FILES[file_idx]}{rank}"] = ch
                file_idx += 1
        if file_idx != 8:
            raise ValueError("Invalid FEN rank width")
    return board, fields[1]


class NeuroChessGui(tk.Tk):
    def __init__(self, engine_path: Path | None = None):
        super().__init__()
        self.title("NeuroChess GUI")
        self.geometry("1040x760")
        self.minsize(880, 650)

        self.root_dir = Path(__file__).resolve().parents[2]
        self.engine_path = engine_path or find_default_engine(self.root_dir)
        self.engine_path_var = tk.StringVar(value=str(self.engine_path) if self.engine_path else "")
        self.engine: UciClient | None = None
        self.engine_events: "queue.Queue[str]" = queue.Queue()
        self.engine_thinking = False
        self.pending_engine_move = False

        self.fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self.pieces, self.side_to_move = parse_fen_board(self.fen)
        self.legal_moves: list[str] = []
        self.moves: list[str] = []
        self.selected: str | None = None
        self.last_move: str | None = None
        self.in_check = False
        self.human_white = True

        self.depth_var = tk.IntVar(value=5)
        self.movetime_var = tk.IntVar(value=0)
        self.side_var = tk.StringVar(value="White")
        self.status_var = tk.StringVar(value="Connect engine to start")
        self.eval_var = tk.StringVar(value="—")
        self.depth_info_var = tk.StringVar(value="0")
        self.nodes_var = tk.StringVar(value="0")
        self.nps_var = tk.StringVar(value="0")
        self.pv_var = tk.StringVar(value="—")

        self._build_ui()
        self._redraw_board()
        self.after(40, self._poll_engine_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.engine_path:
            self.after(100, self._connect_engine)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=12); outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1); outer.rowconfigure(0, weight=1)
        left = ttk.Frame(outer); left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.canvas = tk.Canvas(left, width=640, height=640, highlightthickness=0)
        self.canvas.pack(); self.canvas.bind("<Button-1>", self._on_board_click)

        right = ttk.Frame(outer); right.grid(row=0, column=1, sticky="nsew"); right.columnconfigure(0, weight=1)
        game = ttk.LabelFrame(right, text="Game", padding=10); game.grid(row=0, column=0, sticky="ew", pady=(0,10))
        ttk.Label(game, text="Play as:").grid(row=0,column=0,sticky="w")
        ttk.Combobox(game,textvariable=self.side_var,values=["White","Black"],state="readonly",width=10).grid(row=0,column=1,padx=6)
        ttk.Button(game,text="New game",command=self._new_game).grid(row=0,column=2,padx=6)
        ttk.Button(game,text="Undo",command=self._undo).grid(row=0,column=3)

        search = ttk.LabelFrame(right,text="Search",padding=10); search.grid(row=1,column=0,sticky="ew",pady=(0,10))
        ttk.Label(search,text="Depth:").grid(row=0,column=0,sticky="w")
        ttk.Spinbox(search,from_=1,to=30,textvariable=self.depth_var,width=7).grid(row=0,column=1,padx=6)
        ttk.Label(search,text="Move time ms (0 = depth):").grid(row=1,column=0,sticky="w",pady=(6,0))
        ttk.Spinbox(search,from_=0,to=600000,increment=100,textvariable=self.movetime_var,width=10).grid(row=1,column=1,padx=6,pady=(6,0))
        ttk.Button(search,text="Stop search",command=self._stop_search).grid(row=2,column=0,columnspan=2,sticky="ew",pady=(8,0))

        eng = ttk.LabelFrame(right,text="Engine",padding=10); eng.grid(row=2,column=0,sticky="ew",pady=(0,10)); eng.columnconfigure(0,weight=1)
        ttk.Entry(eng,textvariable=self.engine_path_var).grid(row=0,column=0,sticky="ew")
        ttk.Button(eng,text="Browse…",command=self._browse_engine).grid(row=0,column=1,padx=(6,0))
        ttk.Button(eng,text="Connect",command=self._connect_engine).grid(row=1,column=0,columnspan=2,sticky="ew",pady=(6,0))

        info = ttk.LabelFrame(right,text="Analysis",padding=10); info.grid(row=3,column=0,sticky="nsew",pady=(0,10)); info.columnconfigure(1,weight=1)
        for r,(label,var) in enumerate([("Evaluation",self.eval_var),("Depth",self.depth_info_var),("Nodes",self.nodes_var),("NPS",self.nps_var),("PV",self.pv_var)]):
            ttk.Label(info,text=label+":").grid(row=r,column=0,sticky="nw",padx=(0,8),pady=2)
            ttk.Label(info,textvariable=var,wraplength=300).grid(row=r,column=1,sticky="nw",pady=2)
        status = ttk.LabelFrame(right,text="Status",padding=10); status.grid(row=4,column=0,sticky="ew")
        ttk.Label(status,textvariable=self.status_var,wraplength=320).pack(anchor="w")

    def _human_side(self) -> str:
        return "w" if self.human_white else "b"

    def _orientation_white(self) -> bool:
        return self.human_white

    @staticmethod
    def _sq(file_idx: int, rank_idx: int) -> str:
        return f"{FILES[file_idx]}{rank_idx+1}"

    def _square_from_display(self,row:int,col:int)->str:
        if self._orientation_white():
            return self._sq(col,7-row)
        return self._sq(7-col,row)

    def _display_from_square(self,sq:str)->tuple[int,int]:
        f=FILES.index(sq[0]); r=int(sq[1])-1
        return (7-r,f) if self._orientation_white() else (r,7-f)

    def _redraw_board(self)->None:
        self.canvas.delete("all"); size=min(self.canvas.winfo_width() or 640,self.canvas.winfo_height() or 640); cell=size/8
        targets={m[2:4] for m in self.legal_moves if self.selected and m[:2]==self.selected}
        last={self.last_move[:2],self.last_move[2:4]} if self.last_move else set()
        for row in range(8):
            for col in range(8):
                sq=self._square_from_display(row,col); f=FILES.index(sq[0]); r=int(sq[1])-1
                base=LIGHT if (f+r)%2 else DARK
                color=SELECTED if sq==self.selected else TARGET if sq in targets else LAST if sq in last else base
                x0,y0=col*cell,row*cell
                self.canvas.create_rectangle(x0,y0,x0+cell,y0+cell,fill=color,outline=color)
                ch=self.pieces.get(sq)
                if ch: self.canvas.create_text(x0+cell/2,y0+cell/2,text=PIECES[ch],font=("Segoe UI Symbol",int(cell*.68)))
                if col==0: self.canvas.create_text(x0+5,y0+4,text=sq[1],anchor="nw",font=("Segoe UI",9,"bold"))
                if row==7: self.canvas.create_text(x0+cell-5,y0+cell-4,text=sq[0],anchor="se",font=("Segoe UI",9,"bold"))

    def _on_board_click(self,event)->None:
        if not self.engine or self.engine_thinking or self.side_to_move!=self._human_side() or not self.legal_moves: return
        cell=self.canvas.winfo_width()/8; col,row=int(event.x//cell),int(event.y//cell)
        if not(0<=row<8 and 0<=col<8): return
        sq=self._square_from_display(row,col)
        if self.selected is None:
            ch=self.pieces.get(sq)
            if ch and (ch.isupper()==self.human_white): self.selected=sq; self._redraw_board()
            return
        candidates=[m for m in self.legal_moves if m[:2]==self.selected and m[2:4]==sq]
        if candidates:
            move=self._choose_promotion(candidates)
            if move: self._play_human_move(move)
            return
        ch=self.pieces.get(sq); self.selected=sq if ch and (ch.isupper()==self.human_white) else None; self._redraw_board()

    def _choose_promotion(self,candidates:list[str])->str|None:
        if len(candidates)==1:return candidates[0]
        top=tk.Toplevel(self);top.title("Promotion");top.transient(self);top.grab_set();result=[]
        for suffix,name in [("q","Queen"),("r","Rook"),("b","Bishop"),("n","Knight")]:
            move=next((m for m in candidates if len(m)==5 and m[4]==suffix),None)
            if move: ttk.Button(top,text=name,command=lambda m=move:(result.append(m),top.destroy())).pack(fill="x",padx=12,pady=4)
        self.wait_window(top);return result[0] if result else None

    def _set_position(self)->None:
        assert self.engine
        self.engine.send("position startpos"+(" moves "+" ".join(self.moves) if self.moves else ""))

    def _refresh_state(self)->None:
        if not self.engine:return
        self._set_position();self.engine.send("nc_fen");self.engine.send("nc_legalmoves");self.engine.send("nc_incheck")

    def _play_human_move(self,move:str)->None:
        self.moves.append(move);self.last_move=move;self.selected=None;self.pending_engine_move=True;self._refresh_state()

    def _request_engine_move(self)->None:
        if not self.engine or self.side_to_move==self._human_side() or not self.legal_moves:return
        self.engine_thinking=True;self.status_var.set("NeuroChess is thinking…");self._set_position()
        mt=max(0,int(self.movetime_var.get()))
        self.engine.send(f"go movetime {mt}" if mt>0 else f"go depth {max(1,int(self.depth_var.get()))}")

    def _poll_engine_events(self)->None:
        try:
            while True:
                line=self.engine_events.get_nowait()
                if line.startswith("info depth "):
                    info=parse_info_line(line)
                    if info:
                        self.eval_var.set(f"Mate {info.mate:+d}" if info.mate is not None else (f"{info.score_cp/100:+.2f}" if info.score_cp is not None else "—"))
                        self.depth_info_var.set(f"{info.depth} (sel {info.seldepth})");self.nodes_var.set(f"{info.nodes:,}");self.nps_var.set(f"{info.nps:,}");self.pv_var.set(" ".join(info.pv) if info.pv else "—")
                elif line.startswith("info string nc_fen "):
                    self.fen=line[len("info string nc_fen "):];self.pieces,self.side_to_move=parse_fen_board(self.fen);self._redraw_board();self._update_status()
                elif line.startswith("info string nc_legalmoves"):
                    tail=line[len("info string nc_legalmoves"):].strip();self.legal_moves=tail.split() if tail else [];self._redraw_board();self._update_status()
                    if self.pending_engine_move and self.side_to_move!=self._human_side() and self.legal_moves:
                        self.pending_engine_move=False;self.after(20,self._request_engine_move)
                elif line.startswith("info string nc_incheck "):
                    self.in_check=line.endswith(" 1");self._update_status()
                elif line.startswith("bestmove "):
                    self._handle_bestmove(line.split(maxsplit=1)[1].strip())
                elif line=="readyok":
                    self._refresh_state()
        except queue.Empty: pass
        self.after(40,self._poll_engine_events)

    def _handle_bestmove(self,uci:str)->None:
        self.engine_thinking=False
        if uci!="0000": self.moves.append(uci);self.last_move=uci
        self._refresh_state()

    def _update_status(self)->None:
        if not self.engine:return
        if not self.legal_moves:
            self.status_var.set("Checkmate." if self.in_check else "Draw by stalemate.")
        elif self.engine_thinking:self.status_var.set("NeuroChess is thinking…")
        elif self.in_check:self.status_var.set("Check. Your move." if self.side_to_move==self._human_side() else "Check.")
        else:self.status_var.set("Your move." if self.side_to_move==self._human_side() else "NeuroChess to move.")

    def _new_game(self)->None:
        self._stop_search();self.moves.clear();self.selected=None;self.last_move=None;self.human_white=self.side_var.get()=="White"
        self.eval_var.set("—");self.depth_info_var.set("0");self.nodes_var.set("0");self.nps_var.set("0");self.pv_var.set("—")
        self.pending_engine_move=not self.human_white
        if self.engine:self.engine.send("ucinewgame");self.engine.send("isready")
        self._redraw_board()

    def _undo(self)->None:
        self._stop_search();self.pending_engine_move=False;remove=min(2,len(self.moves));
        if remove:self.moves=self.moves[:-remove]
        self.last_move=self.moves[-1] if self.moves else None;self.selected=None;self._refresh_state()

    def _stop_search(self)->None:
        if self.engine:self.engine.stop()
        self.engine_thinking=False

    def _browse_engine(self)->None:
        path=filedialog.askopenfilename(title="Select NeuroChess engine",filetypes=[("Executable","*.exe"),("All files","*")])
        if path:self.engine_path_var.set(path)

    def _connect_engine(self)->None:
        path=self.engine_path_var.get().strip()
        if not path:messagebox.showerror("NeuroChess","Build the engine first or select neurochess.exe.");return
        try:
            if self.engine:self.engine.close()
            self.engine=UciClient(Path(path),on_line=self.engine_events.put);self.engine.start();self.engine.send("isready");self.status_var.set("Connecting…")
        except Exception as ex:
            self.engine=None;messagebox.showerror("NeuroChess",f"Could not start engine:\n{ex}")

    def _on_close(self)->None:
        if self.engine:self.engine.close()
        self.destroy()


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description="NeuroChess local GUI");parser.add_argument("--engine",type=Path,default=None)
    args=parser.parse_args(argv);app=NeuroChessGui(args.engine);app.mainloop();return 0

if __name__=="__main__":raise SystemExit(main())

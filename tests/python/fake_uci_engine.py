#!/usr/bin/env python3
import sys

for raw in sys.stdin:
    command = raw.strip()
    if command == "uci":
        print("id name FakeUCI 1.0", flush=True)
        print("id author NeuroChess tests", flush=True)
        print("option name Skill type spin default 1 min 1 max 20", flush=True)
        print("option name UCI_LimitStrength type check default false", flush=True)
        print("option name UCI_Elo type spin default 1600 min 1000 max 3200", flush=True)
        print("uciok", flush=True)
    elif command == "isready":
        print("readyok", flush=True)
    elif command.startswith("go"):
        print("info depth 1 score cp 0 nodes 1", flush=True)
        print("bestmove e2e4", flush=True)
    elif command == "quit":
        break

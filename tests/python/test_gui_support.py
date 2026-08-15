import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from python.gui.app import parse_fen_board
from python.gui.uci_client import parse_info_line

class GuiSupportTests(unittest.TestCase):
    def test_parse_cp_info(self):
        info=parse_info_line("info depth 7 seldepth 11 score cp 83 nodes 12345 nps 456789 time 27 pv e2e4 e7e5")
        self.assertEqual((info.depth,info.seldepth,info.score_cp,info.nodes),(7,11,83,12345));self.assertEqual(info.pv,["e2e4","e7e5"])
    def test_parse_mate_info(self):
        info=parse_info_line("info depth 5 seldepth 8 score mate -3 nodes 44 nps 1000 time 4 pv h7h8q");self.assertEqual(info.mate,-3);self.assertIsNone(info.score_cp)
    def test_non_info_returns_none(self):self.assertIsNone(parse_info_line("bestmove e2e4"))
    def test_parse_start_fen(self):
        pieces,side=parse_fen_board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        self.assertEqual(len(pieces),32);self.assertEqual(pieces["e1"],"K");self.assertEqual(pieces["e8"],"k");self.assertEqual(side,"w")

if __name__=="__main__":unittest.main()

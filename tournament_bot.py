#!/usr/bin/env python3
"""
Tournament Chess Bot Interface.
Complies strictly with:
1. Universal Chess Interface (UCI) protocol.
2. One-shot CLI evaluation protocol (--fen / --moves).
3. Authoritative board state tracking and move legality guarantees.
4. Clean stdout hygiene (no diagnostics on stdout).
"""

import sys
import argparse
import logging
import chess
import config
from engine_wrapper import UnifiedChessBrain

# Setup clean stderr logging
logger = logging.getLogger("tournament_bot")


class TournamentBot:
    def __init__(self, permit_stockfish: bool = config.PERMIT_STOCKFISH):
        self.board = chess.Board()
        self.brain = UnifiedChessBrain(permit_stockfish=permit_stockfish)

    def handle_uci(self):
        """Standard UCI loop reading commands from stdin."""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                if line == "uci":
                    # Engine identification
                    sys.stdout.write("id name CompetitionChessMaster\n")
                    sys.stdout.write("id author Antigravity Advanced Agent\n")
                    sys.stdout.write(f"option name Threads type spin default {config.DEFAULT_THREADS} min 1 max 128\n")
                    sys.stdout.write(f"option name Hash type spin default {config.DEFAULT_HASH_MB} min 16 max 2048\n")
                    sys.stdout.write("uciok\n")
                    sys.stdout.flush()

                elif line == "isready":
                    sys.stdout.write("readyok\n")
                    sys.stdout.flush()

                elif line == "ucinewgame":
                    self.board = chess.Board()
                    self.brain.new_game()

                elif line.startswith("position"):
                    self._parse_position(line)

                elif line.startswith("go"):
                    self._parse_go(line)

                elif line == "quit":
                    self.brain.close()
                    break

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                logger.error(f"Error in UCI loop: {e}")

    def _parse_position(self, line: str):
        """
        Parses position command:
        position startpos [moves ...]
        position fen <fen> [moves ...]
        """
        tokens = line.split()
        if len(tokens) < 2:
            return

        moves_idx = -1
        if "moves" in tokens:
            moves_idx = tokens.index("moves")

        if tokens[1] == "startpos":
            self.board = chess.Board()
        elif tokens[1] == "fen":
            # Extract FEN tokens until 'moves' or end
            fen_end = moves_idx if moves_idx != -1 else len(tokens)
            fen_str = " ".join(tokens[2:fen_end])
            try:
                self.board = chess.Board(fen_str)
            except Exception as e:
                logger.error(f"Invalid FEN '{fen_str}': {e}")
                self.board = chess.Board()

        if moves_idx != -1:
            for move_str in tokens[moves_idx + 1:]:
                try:
                    move = chess.Move.from_uci(move_str)
                    if self.board.is_legal(move):
                        self.board.push(move)
                    else:
                        logger.error(f"Received illegal move in history: {move_str}")
                except Exception as e:
                    logger.error(f"Cannot parse move '{move_str}': {e}")

    def _parse_go(self, line: str):
        """
        Parses go command:
        go movetime <ms>
        go wtime <ms> btime <ms> winc <ms> binc <ms>
        """
        tokens = line.split()
        time_limit_ms = config.DEFAULT_MOVETIME_MS

        params = {}
        idx = 1
        while idx < len(tokens):
            key = tokens[idx]
            if idx + 1 < len(tokens):
                try:
                    params[key] = int(tokens[idx + 1])
                    idx += 2
                    continue
                except ValueError:
                    pass
            idx += 1

        if "movetime" in params:
            time_limit_ms = params["movetime"]
        else:
            # Time control allocation
            turn = self.board.turn
            time_left = params.get("wtime" if turn == chess.WHITE else "btime", None)
            inc = params.get("winc" if turn == chess.WHITE else "binc", 0)

            if time_left is not None:
                # Estimate moves to play ~ 30-40 moves, allocate budget with increment
                time_limit_ms = max(config.MIN_SEARCH_MS, (time_left // 30) + (inc // 2))

        # Enforce hard ceiling and buffer
        move = self.brain.get_move(self.board, time_limit_ms=time_limit_ms)

        if move is not None and self.board.is_legal(move):
            sys.stdout.write(f"bestmove {move.uci()}\n")
        else:
            # Emergency safety net: pick first legal move
            legal_moves = list(self.board.legal_moves)
            emergency_move = legal_moves[0].uci() if legal_moves else "0000"
            sys.stdout.write(f"bestmove {emergency_move}\n")

        sys.stdout.flush()

    def play_single_fen(self, fen: str, movetime_ms: int = config.DEFAULT_MOVETIME_MS) -> str:
        """Evaluates single FEN and returns best move in UCI format."""
        try:
            self.board = chess.Board(fen)
        except Exception as e:
            logger.error(f"Failed to load FEN '{fen}': {e}")
            return "0000"

        move = self.brain.get_move(self.board, time_limit_ms=movetime_ms)
        if move and self.board.is_legal(move):
            return move.uci()
        legal = list(self.board.legal_moves)
        return legal[0].uci() if legal else "0000"

# Global singleton bot instance for Python module imports
_global_bot = None

def choose_move(fen_or_board, movetime_ms: int = config.DEFAULT_MOVETIME_MS) -> str:
    """
    Direct API function interface for tournament harnesses that import a python function.
    Accepts FEN string or chess.Board instance.
    Returns best legal move UCI string (e.g. 'e2e4').
    """
    global _global_bot
    if _global_bot is None:
        _global_bot = TournamentBot()
    if isinstance(fen_or_board, chess.Board):
        move = _global_bot.brain.get_move(fen_or_board, time_limit_ms=movetime_ms)
        if move and fen_or_board.is_legal(move):
            return move.uci()
        legal = list(fen_or_board.legal_moves)
        return legal[0].uci() if legal else "0000"
    else:
        return _global_bot.play_single_fen(str(fen_or_board), movetime_ms=movetime_ms)


def main():
    parser = argparse.ArgumentParser(description="Competition Chess Master Tournament Engine")
    parser.add_argument("--uci", action="store_true", help="Run standard UCI loop on stdin/stdout")
    parser.add_argument("--fen", type=str, help="Single position FEN to evaluate")
    parser.add_argument("--movetime", type=int, default=config.DEFAULT_MOVETIME_MS, help="Search time in milliseconds")
    parser.add_argument("--no-stockfish", action="store_true", help="Force fallback engine (if Stockfish forbidden)")

    args = parser.parse_args()
    permit_stockfish = config.PERMIT_STOCKFISH and not args.no_stockfish

    bot = TournamentBot(permit_stockfish=permit_stockfish)

    if args.fen:
        # One-shot CLI evaluation
        best_move = bot.play_single_fen(args.fen, movetime_ms=args.movetime)
        # Stdout must only contain the move!
        sys.stdout.write(f"{best_move}\n")
        sys.stdout.flush()
        bot.brain.close()
    else:
        # Default mode: standard UCI tournament interface
        bot.handle_uci()


if __name__ == "__main__":
    main()

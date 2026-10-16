import os
import sys
import time
import subprocess
import logging
import chess
import config

logger = logging.getLogger("tournament_bot")
logger.setLevel(logging.INFO)
# Output logs strictly to stderr so stdout remains 100% clean for tournament protocol
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s: %(message)s"))
logger.addHandler(stderr_handler)


class FallbackEngine:
    """
    High-reliability, tactical internal engine.
    Uses Alpha-Beta search with Quiescence, Piece-Square Tables,
    MVV-LVA move ordering, and strict legality validation.
    Used when Stockfish binary is unavailable or prohibited by tournament rules.
    """

    PIECE_VALUES = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 20000,
    }

    # Positional piece-square bonus tables (from White's perspective)
    PST = {
        chess.PAWN: [
            0,  0,  0,  0,  0,  0,  0,  0,
            50, 50, 50, 50, 50, 50, 50, 50,
            10, 10, 20, 30, 30, 20, 10, 10,
             5,  5, 10, 25, 25, 10,  5,  5,
             0,  0,  0, 20, 20,  0,  0,  0,
             5, -5,-10,  0,  0,-10, -5,  5,
             5, 10, 10,-20,-20, 10, 10,  5,
             0,  0,  0,  0,  0,  0,  0,  0
        ],
        chess.KNIGHT: [
            -50,-40,-30,-30,-30,-30,-40,-50,
            -40,-20,  0,  0,  0,  0,-20,-40,
            -30,  0, 10, 15, 15, 10,  0,-30,
            -30,  5, 15, 20, 20, 15,  5,-30,
            -30,  0, 15, 20, 20, 15,  0,-30,
            -30,  5, 10, 15, 15, 10,  5,-30,
            -40,-20,  0,  5,  5,  0,-20,-40,
            -50,-40,-30,-30,-30,-30,-40,-50,
        ],
        chess.BISHOP: [
            -20,-10,-10,-10,-10,-10,-10,-20,
            -10,  0,  0,  0,  0,  0,  0,-10,
            -10,  0,  5, 10, 10,  5,  0,-10,
            -10,  5,  5, 10, 10,  5,  5,-10,
            -10,  0, 10, 10, 10, 10,  0,-10,
            -10, 10, 10, 10, 10, 10, 10,-10,
            -10,  5,  0,  0,  0,  0,  5,-10,
            -20,-10,-10,-10,-10,-10,-10,-20,
        ],
        chess.ROOK: [
              0,  0,  0,  0,  0,  0,  0,  0,
              5, 10, 10, 10, 10, 10, 10,  5,
             -5,  0,  0,  0,  0,  0,  0, -5,
             -5,  0,  0,  0,  0,  0,  0, -5,
             -5,  0,  0,  0,  0,  0,  0, -5,
             -5,  0,  0,  0,  0,  0,  0, -5,
             -5,  0,  0,  0,  0,  0,  0, -5,
              0,  0,  0,  5,  5,  0,  0,  0
        ],
        chess.QUEEN: [
            -20,-10,-10, -5, -5,-10,-10,-20,
            -10,  0,  0,  0,  0,  0,  0,-10,
            -10,  0,  5,  5,  5,  5,  0,-10,
             -5,  0,  5,  5,  5,  5,  0, -5,
              0,  0,  5,  5,  5,  5,  0, -5,
            -10,  5,  5,  5,  5,  5,  0,-10,
            -10,  0,  5,  0,  0,  0,  0,-10,
            -20,-10,-10, -5, -5,-10,-10,-20
        ],
        chess.KING: [
            -30,-40,-40,-50,-50,-40,-40,-30,
            -30,-40,-40,-50,-50,-40,-40,-30,
            -30,-40,-40,-50,-50,-40,-40,-30,
            -30,-40,-40,-50,-50,-40,-40,-30,
            -20,-30,-30,-40,-40,-30,-30,-20,
            -10,-20,-20,-20,-20,-20,-20,-10,
             20, 20,  0,  0,  0,  0, 20, 20,
             20, 30, 10,  0,  0, 10, 30, 20
        ]
    }

    def evaluate_board(self, board: chess.Board) -> int:
        """Heuristic evaluation from the perspective of White."""
        if board.is_checkmate():
            return -99999 if board.turn == chess.WHITE else 99999
        if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
            return 0

        score = 0
        for square, piece in board.piece_map().items():
            val = self.PIECE_VALUES[piece.piece_type]
            pst_table = self.PST[piece.piece_type]
            pst_idx = square if piece.color == chess.WHITE else chess.square_mirror(square)
            pst_val = pst_table[pst_idx]
            total_val = val + pst_val
            if piece.color == chess.WHITE:
                score += total_val
            else:
                score -= total_val

        # Mobility bonus
        turn_mult = 1 if board.turn == chess.WHITE else -1
        score += turn_mult * (board.legal_moves.count() * 5)
        return score

    def order_moves(self, board: chess.Board, moves):
        """Orders captures and promotions first for faster alpha-beta cutoffs."""
        def move_score(move: chess.Move):
            score = 0
            if board.is_capture(move):
                victim_type = board.piece_type_at(move.to_square) or chess.PAWN
                attacker_type = board.piece_type_at(move.from_square) or chess.PAWN
                score += 1000 + self.PIECE_VALUES[victim_type] - self.PIECE_VALUES[attacker_type] // 10
            if move.promotion:
                score += 800
            if board.gives_check(move):
                score += 300
            return score

        return sorted(moves, key=move_score, reverse=True)

    def quiescence(self, board: chess.Board, alpha: int, beta: int, depth: int = 4) -> int:
        """Quiescence search to avoid the horizon effect on tactical captures."""
        stand_pat = self.evaluate_board(board)
        if board.turn == chess.BLACK:
            stand_pat = -stand_pat

        if depth <= 0:
            return stand_pat
        if stand_pat >= beta:
            return beta
        if alpha < stand_pat:
            alpha = stand_pat

        capture_moves = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
        for move in self.order_moves(board, capture_moves):
            board.push(move)
            score = -self.quiescence(board, -beta, -alpha, depth - 1)
            board.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def alpha_beta(self, board: chess.Board, depth: int, alpha: int, beta: int, end_time: float) -> int:
        if time.time() >= end_time:
            return self.quiescence(board, alpha, beta)

        if depth == 0 or board.is_game_over():
            return self.quiescence(board, alpha, beta)

        best_score = -100000
        for move in self.order_moves(board, board.legal_moves):
            board.push(move)
            score = -self.alpha_beta(board, depth - 1, -beta, -alpha, end_time)
            board.pop()

            if score > best_score:
                best_score = score
            if best_score > alpha:
                alpha = best_score
            if alpha >= beta:
                break
        return best_score

    def get_best_move(self, board: chess.Board, time_limit_ms: int = 500) -> chess.Move:
        """Iterative deepening alpha-beta search within time budget."""
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None
        if len(legal_moves) == 1:
            return legal_moves[0]

        start_time = time.time()
        end_time = start_time + max(0.01, (time_limit_ms / 1000.0) * 0.8)

        # Immediate checkmate check
        for move in legal_moves:
            board.push(move)
            if board.is_checkmate():
                board.pop()
                return move
            board.pop()

        best_move = legal_moves[0]
        max_depth = 4
        try:
            for depth in range(1, max_depth + 1):
                if time.time() >= end_time:
                    break
                current_best = None
                alpha = -100000
                beta = 100000

                for move in self.order_moves(board, legal_moves):
                    if time.time() >= end_time:
                        break
                    board.push(move)
                    score = -self.alpha_beta(board, depth - 1, -beta, -alpha, end_time)
                    board.pop()

                    if score > alpha:
                        alpha = score
                        current_best = move
                if current_best:
                    best_move = current_best
        except Exception as e:
            logger.warning(f"Fallback search interrupted: {e}")

        return best_move


class StockfishEngine:
    """
    Subprocess-based persistent UCI interface to Stockfish.
    Reuses process across moves, configures threads and hash,
    enforces per-move safety margins, and handles crash recovery.
    """

    def __init__(self, binary_path: str = config.STOCKFISH_BIN_PATH,
                 threads: int = config.DEFAULT_THREADS,
                 hash_mb: int = config.DEFAULT_HASH_MB):
        self.binary_path = binary_path
        self.threads = threads
        self.hash_mb = hash_mb
        self.process = None
        self._is_ready = False
        self._start_process()

    def _start_process(self):
        """Spawns persistent engine process and configures UCI settings."""
        if not os.path.exists(self.binary_path):
            logger.error(f"Stockfish binary not found at: {self.binary_path}")
            self.process = None
            return

        try:
            self.process = subprocess.Popen(
                [self.binary_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            # Send UCI initialization
            self._send_command("uci")
            self._wait_for_response("uciok", timeout=5.0)

            # Configure performance parameters
            self._send_command(f"setoption name Threads value {self.threads}")
            self._send_command(f"setoption name Hash value {self.hash_mb}")
            self._send_command(f"setoption name Move Overhead value {config.SAFETY_MARGIN_MS}")

            self._send_command("isready")
            self._wait_for_response("readyok", timeout=5.0)
            self._is_ready = True
            logger.info(f"Stockfish engine initialized with {self.threads} threads, {self.hash_mb}MB hash.")
        except Exception as e:
            logger.error(f"Failed to start Stockfish process: {e}")
            self.process = None
            self._is_ready = False

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def restart_if_needed(self):
        if not self.is_alive():
            logger.warning("Stockfish process dead or unresponsive. Restarting...")
            self._start_process()

    def _send_command(self, cmd: str):
        if not self.is_alive():
            return
        try:
            self.process.stdin.write(cmd + "\n")
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f"Error sending command '{cmd}' to Stockfish: {e}")

    def _wait_for_response(self, expected: str, timeout: float = 3.0) -> bool:
        """Reads lines until expected string is in line or timeout expires."""
        if not self.is_alive():
            return False
        start = time.time()
        while time.time() - start < timeout:
            line = self.process.stdout.readline()
            if not line:
                time.sleep(0.01)
                continue
            line = line.strip()
            if expected in line:
                return True
        return False

    def new_game(self):
        """Prepares engine for a new game."""
        self.restart_if_needed()
        self._send_command("ucinewgame")
        self._send_command("isready")
        self._wait_for_response("readyok", timeout=3.0)

    def search_best_move(self, board: chess.Board, time_limit_ms: int = 1000) -> chess.Move:
        """
        Sends full position history and searches for best move within time budget.
        """
        self.restart_if_needed()
        if not self.is_alive():
            return None

        # Build position command with complete FEN (including halfmove, fullmove, castling rights)
        fen = board.fen()
        self._send_command(f"position fen {fen}")

        # Compute safe search time leaving margin for I/O and pipe buffer
        effective_search_ms = max(config.MIN_SEARCH_MS, time_limit_ms - config.SAFETY_MARGIN_MS)
        self._send_command(f"go movetime {effective_search_ms}")

        # Wait for bestmove response with safety timeout
        timeout = (effective_search_ms / 1000.0) + 2.0
        start_time = time.time()
        best_move_str = None

        while time.time() - start_time < timeout:
            try:
                line = self.process.stdout.readline()
            except Exception as e:
                logger.error(f"Error reading from Stockfish stdout: {e}")
                break
            if not line:
                time.sleep(0.01)
                continue
            line = line.strip()
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) >= 2:
                    best_move_str = parts[1]
                break

        if not best_move_str or best_move_str == "(none)":
            logger.warning("Stockfish did not produce a valid move.")
            return None

        try:
            move = chess.Move.from_uci(best_move_str)
            if board.is_legal(move):
                return move
            else:
                logger.error(f"Stockfish produced illegal move: {best_move_str}")
                return None
        except Exception as e:
            logger.error(f"Failed to parse Stockfish move '{best_move_str}': {e}")
            return None

    def close(self):
        """Gracefully terminates Stockfish process."""
        if self.is_alive():
            try:
                self._send_command("quit")
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                pass
            finally:
                self.process = None


class UnifiedChessBrain:
    """
    Main Tournament Chess Brain.
    Orchestrates the primary engine (Stockfish 19) and tactical fallback engine.
    Guarantees 100% legal moves, safe time budgeting, and crash resilience.
    """

    def __init__(self, permit_stockfish: bool = config.PERMIT_STOCKFISH):
        self.permit_stockfish = permit_stockfish
        self.stockfish = None
        self.fallback = FallbackEngine()

        if self.permit_stockfish and os.path.exists(config.STOCKFISH_BIN_PATH):
            self.stockfish = StockfishEngine()
            if not self.stockfish.is_alive():
                logger.warning("Stockfish initialization failed. Using FallbackEngine.")
                self.stockfish = None
        else:
            logger.info("Stockfish disabled or binary not found. Using FallbackEngine.")

    def new_game(self):
        if self.stockfish:
            self.stockfish.new_game()

    def get_move(self, board: chess.Board, time_limit_ms: int = config.DEFAULT_MOVETIME_MS) -> chess.Move:
        """
        Calculates and verifies the best legal move.
        1. Checks terminal state / single move fast path.
        2. Queries Stockfish if active.
        3. If Stockfish fails, times out, or produces invalid move, queries FallbackEngine.
        4. Verifies absolute legality against authoritative board state.
        """
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None
        if len(legal_moves) == 1:
            return legal_moves[0]

        # 1. Attempt Stockfish
        if self.stockfish:
            if not self.stockfish.is_alive():
                self.stockfish.restart_if_needed()
            if self.stockfish.is_alive():
                try:
                    move = self.stockfish.search_best_move(board, time_limit_ms)
                    if move and board.is_legal(move):
                        return move
                except Exception as e:
                    logger.error(f"Stockfish query failed, triggering fallback: {e}")

        # 2. Safe Fallback
        logger.info("Using FallbackEngine for move calculation.")
        fallback_move = self.fallback.get_best_move(board, max(config.MIN_SEARCH_MS, time_limit_ms - config.SAFETY_MARGIN_MS))
        if fallback_move and board.is_legal(fallback_move):
            return fallback_move

        # 3. Absolute safety net: any legal move
        return legal_moves[0]

    def close(self):
        if self.stockfish:
            self.stockfish.close()

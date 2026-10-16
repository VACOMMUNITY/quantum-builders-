#!/usr/bin/env python3
"""
Comprehensive Independent Verification and Tournament Test Suite.
Tests:
1. Stockfish binary startup, executable path, version, and UCI handshake.
2. Legal move generation for White and Black.
3. Kingside and Queenside castling for White and Black.
4. En passant capture for White and Black.
5. Pawn promotion for White and Black.
6. Checkmate detection for White and Black.
7. Stalemate: terminal recognition and accidental stalemate avoidance.
8. Engine crash recovery: simulates subprocess kill and verifies automatic recovery.
9. Move timeout deadline enforcement.
10. Terminal state safety (zero illegal moves generated on game over).
11. Paired benchmark games against baselines (White & Black) with complete win/draw/loss tracking.
"""

import os
import sys
import time
import random
import logging
import chess
import config
from engine_wrapper import UnifiedChessBrain, FallbackEngine, StockfishEngine

logging.basicConfig(level=logging.INFO, format="[VERIFY] %(message)s")


def test_stockfish_handshake():
    logging.info("--- [1] Stockfish Startup, Path & UCI Handshake ---")
    bin_path = config.STOCKFISH_BIN_PATH
    assert os.path.exists(bin_path), f"Stockfish binary does not exist at {bin_path}"
    logging.info(f"Verified binary path: {bin_path}")

    engine = StockfishEngine(binary_path=bin_path, threads=config.DEFAULT_THREADS, hash_mb=config.DEFAULT_HASH_MB)
    assert engine.is_alive(), "Stockfish engine process failed to start or is not alive"
    assert engine._is_ready, "Stockfish engine did not complete UCI handshake ('readyok')"
    logging.info(f"Engine is active (PID: {engine.process.pid})")
    logging.info(f"Configured options: Threads={engine.threads}, Hash={engine.hash_mb}MB")
    engine.close()
    logging.info("PASS: Stockfish startup, binary path, and UCI handshake verified.\n")


def test_tactical_and_rule_edge_cases(brain: UnifiedChessBrain):
    logging.info("--- [2] Comprehensive Chess Rules & Tactical Edge Cases ---")

    # A. White Move Generation & Black Move Generation
    board_start = chess.Board()
    move_w = brain.get_move(board_start, time_limit_ms=200)
    assert move_w in board_start.legal_moves, f"White start move {move_w} illegal"
    logging.info(f"PASS: White opening move valid ({move_w})")

    board_black = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
    move_b = brain.get_move(board_black, time_limit_ms=200)
    assert move_b in board_black.legal_moves, f"Black response move {move_b} illegal"
    logging.info(f"PASS: Black response move valid ({move_b})")

    # B. Castling (Kingside & Queenside for White and Black)
    # White Kingside (e1g1)
    board_w_kcastle = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 1 6")
    move_w_kc = brain.get_move(board_w_kcastle, time_limit_ms=200)
    assert chess.Move.from_uci("e1g1") in board_w_kcastle.legal_moves
    assert board_w_kcastle.is_legal(move_w_kc)
    logging.info(f"PASS: White Kingside castling legal move evaluated ({move_w_kc})")

    # White Queenside (e1c1)
    board_w_qcastle = chess.Board("r3k2r/pppq1ppp/2npbn2/2b1p3/4P3/1PNP1N2/PBPQBPPP/R3K2R w KQkq - 3 9")
    move_w_qc = brain.get_move(board_w_qcastle, time_limit_ms=200)
    assert chess.Move.from_uci("e1c1") in board_w_qcastle.legal_moves
    assert board_w_qcastle.is_legal(move_w_qc)
    logging.info(f"PASS: White Queenside castling legal move evaluated ({move_w_qc})")

    # Black Kingside (e8g8)
    board_b_kcastle = chess.Board("r1bqk2r/pppp1ppp/2n2n2/4p3/1bB1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 2 5")
    move_b_kc = brain.get_move(board_b_kcastle, time_limit_ms=200)
    assert chess.Move.from_uci("e8g8") in board_b_kcastle.legal_moves
    assert board_b_kcastle.is_legal(move_b_kc)
    logging.info(f"PASS: Black Kingside castling legal move evaluated ({move_b_kc})")

    # Black Queenside (e8c8)
    board_b_qcastle = chess.Board("r3k2r/pppq1ppp/2npbn2/4p3/4P3/1PNP1N2/PBPQBPPP/R3K2R b KQkq - 4 9")
    move_b_qc = brain.get_move(board_b_qcastle, time_limit_ms=200)
    assert chess.Move.from_uci("e8c8") in board_b_qcastle.legal_moves
    assert board_b_qcastle.is_legal(move_b_qc)
    logging.info(f"PASS: Black Queenside castling legal move evaluated ({move_b_qc})")

    # C. En Passant Capture (White & Black)
    # White en passant: e5f6
    board_w_ep = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    ep_move_w = chess.Move.from_uci("e5f6")
    assert ep_move_w in board_w_ep.legal_moves
    move_w_ep = brain.get_move(board_w_ep, time_limit_ms=200)
    assert board_w_ep.is_legal(move_w_ep)
    logging.info(f"PASS: White En Passant evaluated legally ({move_w_ep})")

    # Black en passant: d4c3
    board_b_ep = chess.Board("rnbqkbnr/pppp1ppp/8/8/3Pp3/8/PPP1PPPP/RNBQKBNR b KQkq d3 0 3")
    ep_move_b = chess.Move.from_uci("e4d3")
    assert ep_move_b in board_b_ep.legal_moves
    move_b_ep = brain.get_move(board_b_ep, time_limit_ms=200)
    assert board_b_ep.is_legal(move_b_ep)
    logging.info(f"PASS: Black En Passant evaluated legally ({move_b_ep})")

    # D. Pawn Promotion (White to Queen, Black to Queen)
    board_w_promo = chess.Board("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    move_w_pr = brain.get_move(board_w_promo, time_limit_ms=200)
    assert move_w_pr.promotion == chess.QUEEN, f"Expected Queen promotion, got {move_w_pr}"
    logging.info(f"PASS: White promotion to Queen verified ({move_w_pr})")

    board_b_promo = chess.Board("8/K1k5/8/8/8/8/1p6/8 b - - 0 1")
    move_b_pr = brain.get_move(board_b_promo, time_limit_ms=200)
    assert move_b_pr == chess.Move.from_uci("b2b1q"), f"Expected b2b1q promotion for Black, got {move_b_pr}"
    logging.info(f"PASS: Black promotion to Queen verified ({move_b_pr})")

    # E. Checkmate Identification (White & Black)
    # White finds Mate in 1: f3f7#
    board_mate_w = chess.Board("r1bqkb1r/pppp1ppp/2n5/4p3/2B1n3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1")
    move_mate_w = brain.get_move(board_mate_w, time_limit_ms=300)
    assert move_mate_w == chess.Move.from_uci("f3f7"), f"Expected f3f7#, got {move_mate_w}"
    logging.info("PASS: White delivers immediate checkmate (f3f7#)")

    # Black delivers checkmate in 1: d8h4#
    board_mate_b = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2")
    move_mate_b = brain.get_move(board_mate_b, time_limit_ms=300)
    assert move_mate_b == chess.Move.from_uci("d8h4"), f"Expected d8h4# mate by Black, got {move_mate_b}"
    board_mate_b.push(move_mate_b)
    assert board_mate_b.is_checkmate(), "Position after d8h4 should be checkmate"
    logging.info("PASS: Black delivers immediate checkmate (d8h4#)")

    # F. Stalemate: Terminal Position & Accidental Stalemate Avoidance
    # 1. Terminal stalemate position (Black has no legal moves, not in check)
    board_stale = chess.Board("7k/5K2/6Q1/8/8/8/8/8 b - - 0 1")
    assert board_stale.is_stalemate()
    move_stale = brain.get_move(board_stale, time_limit_ms=200)
    assert move_stale is None, f"Expected None on stalemate, got {move_stale}"
    logging.info("PASS: Terminal stalemate returns None without illegal move generation")

    # 2. Winning position: must deliver checkmate, NOT accidental stalemate
    # White King on f7, Queen on d7, Black King on h8
    # Legal move Qh7# is immediate checkmate.
    board_avoid_stale = chess.Board("7k/3Q1K2/8/8/8/8/8/8 w - - 0 1")
    move_check = brain.get_move(board_avoid_stale, time_limit_ms=300)
    board_avoid_stale.push(move_check)
    assert board_avoid_stale.is_checkmate(), f"Engine failed to deliver mate, played {move_check}"
    assert not board_avoid_stale.is_stalemate(), "Engine played stalemate instead of checkmate!"
    logging.info(f"PASS: Accidental stalemate avoided; delivered checkmate with {move_check}\n")


def test_crash_recovery(brain: UnifiedChessBrain):
    logging.info("--- [3] Engine Crash Recovery & Fault-Tolerance Test ---")
    board = chess.Board()

    if brain.stockfish and brain.stockfish.is_alive():
        pid = brain.stockfish.process.pid
        logging.info(f"Simulating sudden engine crash: killing Stockfish process PID {pid}...")
        brain.stockfish.process.kill()
        brain.stockfish.process.wait()
        assert not brain.stockfish.is_alive(), "Failed to kill Stockfish process for crash test"
        logging.info("Process confirmed terminated. Now requesting move from UnifiedChessBrain...")

        # Request move: brain should automatically detect dead process, restart or fallback, and return legal move
        t0 = time.time()
        move = brain.get_move(board, time_limit_ms=300)
        elapsed = time.time() - t0

        assert move is not None, "Brain returned None after engine crash"
        assert move in board.legal_moves, f"Brain returned illegal move {move} after crash"
        logging.info(f"PASS: Engine recovered successfully in {elapsed:.3f}s. Move generated: {move}")
        logging.info(f"Stockfish status after recovery: alive={brain.stockfish.is_alive()}\n")
    else:
        logging.info("Stockfish not currently active; skipping kill simulation.\n")


def test_timeout_compliance(brain: UnifiedChessBrain):
    logging.info("--- [4] Move Deadline & Timeout Compliance ---")
    board = chess.Board()
    target_limits = [100, 250, 500]  # milliseconds

    for limit in target_limits:
        t0 = time.time()
        move = brain.get_move(board, time_limit_ms=limit)
        elapsed_ms = (time.time() - t0) * 1000.0
        assert move in board.legal_moves, f"Illegal move {move} at limit {limit}ms"
        # Search time should not exceed target + overhead tolerance (500ms grace for process IO)
        assert elapsed_ms < limit + 500, f"Engine exceeded time budget: {elapsed_ms:.1f}ms for limit {limit}ms"
        logging.info(f"Limit: {limit:3}ms -> Actual search time: {elapsed_ms:5.1f}ms | Move: {move}")

    logging.info("PASS: Per-move deadline strictly maintained within safe platform margins.\n")


def play_paired_match(white_player, black_player, white_name: str, black_name: str, max_moves: int = 150):
    board = chess.Board()
    move_count = 0
    total_time_w = 0.0
    total_time_b = 0.0
    illegal_moves = 0
    timeouts = 0

    while not board.is_game_over() and move_count < max_moves:
        is_white = (board.turn == chess.WHITE)
        player = white_player if is_white else black_player
        name = white_name if is_white else black_name

        t0 = time.time()
        try:
            if player == "random":
                move = random.choice(list(board.legal_moves))
            elif isinstance(player, FallbackEngine):
                move = player.get_best_move(board, time_limit_ms=150)
            elif isinstance(player, UnifiedChessBrain):
                move = player.get_move(board, time_limit_ms=150)
            else:
                move = random.choice(list(board.legal_moves))
        except Exception as e:
            logging.error(f"Engine exception by {name}: {e}")
            return {"winner": "crash", "moves": move_count, "illegal_moves": 1, "timeouts": 0}

        elapsed = time.time() - t0
        if is_white:
            total_time_w += elapsed
        else:
            total_time_b += elapsed

        if elapsed > 2.0:
            timeouts += 1

        if move not in board.legal_moves:
            logging.error(f"Illegal move by {name}: {move}")
            illegal_moves += 1
            winner = black_name if is_white else white_name
            return {"winner": winner, "moves": move_count, "illegal_moves": illegal_moves, "timeouts": timeouts}

        board.push(move)
        move_count += 1

    if board.is_checkmate():
        winner = black_name if board.turn == chess.WHITE else white_name
        reason = "Checkmate"
    elif board.is_stalemate():
        winner = "Draw"
        reason = "Stalemate"
    elif board.is_insufficient_material():
        winner = "Draw"
        reason = "Insufficient Material"
    elif board.is_seventyfive_moves() or board.is_fivefold_repetition():
        winner = "Draw"
        reason = "Draw Rule (50-move / 3-fold repetition)"
    elif move_count >= max_moves:
        winner = "Draw"
        reason = "Move limit reached"
    else:
        winner = "Draw"
        reason = "Draw"

    return {
        "winner": winner,
        "reason": reason,
        "moves": move_count,
        "illegal_moves": illegal_moves,
        "timeouts": timeouts,
    }


def run_paired_tournament_matches():
    logging.info("--- [5] Full Paired Tournament Matches (Both Colors) ---")
    brain = UnifiedChessBrain(permit_stockfish=True)
    fallback = FallbackEngine()

    matches = [
        # Set 1: Against Legal-Random Baseline (Paired)
        ("Match 1: TournamentBot (White) vs Random (Black)", brain, "random", "TournamentBot", "Random"),
        ("Match 2: Random (White) vs TournamentBot (Black)", "random", brain, "Random", "TournamentBot"),
        # Set 2: Additional Paired Match vs Legal-Random
        ("Match 3: TournamentBot (White) vs Random (Black)", brain, "random", "TournamentBot", "Random"),
        ("Match 4: Random (White) vs TournamentBot (Black)", "random", brain, "Random", "TournamentBot"),
        # Set 3: Against Fallback Tactical Engine Baseline (Paired)
        ("Match 5: TournamentBot (White) vs Fallback (Black)", brain, fallback, "TournamentBot", "Fallback"),
        ("Match 6: Fallback (White) vs TournamentBot (Black)", fallback, brain, "Fallback", "TournamentBot"),
    ]

    results = []
    for label, wp, bp, wn, bn in matches:
        logging.info(f"Playing {label}...")
        res = play_paired_match(wp, bp, wn, bn)
        results.append((label, res))
        logging.info(f"-> Winner: {res['winner']:14} | Moves: {res['moves']:3} | Reason: {res['reason']}")

    brain.close()

    logging.info("\n==========================================")
    logging.info("INDEPENDENT VERIFICATION MATCH AUDIT")
    logging.info("==========================================")
    wins = 0
    draws = 0
    losses = 0
    total_illegal = 0
    total_timeouts = 0

    for label, r in results:
        if r["winner"] == "TournamentBot":
            wins += 1
        elif r["winner"] == "Draw":
            draws += 1
        else:
            losses += 1
        total_illegal += r["illegal_moves"]
        total_timeouts += r["timeouts"]
        logging.info(f"{label:52}: Winner: {r['winner']:14} Moves: {r['moves']:3} ({r['reason']})")

    logging.info("------------------------------------------")
    logging.info(f"TournamentBot Record: {wins} Wins - {draws} Draws - {losses} Losses")
    logging.info(f"Total Illegal Moves: {total_illegal}")
    logging.info(f"Total Timeouts (>2s): {total_timeouts}")
    logging.info("==========================================\n")


if __name__ == "__main__":
    test_stockfish_handshake()
    unified_brain = UnifiedChessBrain(permit_stockfish=True)
    try:
        test_tactical_and_rule_edge_cases(unified_brain)
        test_crash_recovery(unified_brain)
        test_timeout_compliance(unified_brain)
    finally:
        unified_brain.close()
    run_paired_tournament_matches()

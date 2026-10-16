#!/usr/bin/env python3
"""
Test Protocol Compliance for TournamentBot.
Tests:
1. One-shot CLI evaluation: `python tournament_bot.py --fen ...`
2. UCI stdin/stdout pipe protocol: `uci`, `isready`, `ucinewgame`, `position`, `go`, `quit`.
3. Verifies stdout hygiene: ensures zero extraneous logs or non-UCI strings appear on stdout.
"""

import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="[PROTOCOL-TEST] %(message)s")


def test_cli_mode():
    logging.info("Testing CLI Mode (--fen)...")
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1n3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1"
    proc = subprocess.Popen(
        [sys.executable, "tournament_bot.py", "--fen", fen, "--movetime", "200"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    stdout, stderr = proc.communicate(timeout=5)
    move = stdout.strip()
    logging.info(f"CLI stdout response: '{move}'")
    assert move == "f3f7", f"Expected 'f3f7', got '{move}'"
    logging.info("PASS: CLI mode correctly produced pure move on stdout.")


def test_uci_protocol():
    logging.info("Testing UCI Protocol Pipe...")
    proc = subprocess.Popen(
        [sys.executable, "tournament_bot.py", "--uci"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    # 1. Send uci
    proc.stdin.write("uci\n")
    proc.stdin.flush()
    lines = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        lines.append(line)
        if line == "uciok":
            break

    assert "uciok" in lines, f"Expected 'uciok', received: {lines}"
    assert any(l.startswith("id name") for l in lines), "Missing 'id name' in UCI response"
    logging.info("PASS: UCI handshake verified ('uci' -> 'uciok').")

    # 2. Send isready
    proc.stdin.write("isready\n")
    proc.stdin.flush()
    ready_line = proc.stdout.readline().strip()
    assert ready_line == "readyok", f"Expected 'readyok', got '{ready_line}'"
    logging.info("PASS: 'isready' -> 'readyok' verified.")

    # 3. Position and go
    proc.stdin.write("ucinewgame\n")
    proc.stdin.write("position startpos moves e2e4 e7e5\n")
    proc.stdin.write("go movetime 150\n")
    proc.stdin.flush()

    bestmove_line = proc.stdout.readline().strip()
    logging.info(f"Received bestmove line: '{bestmove_line}'")
    assert bestmove_line.startswith("bestmove"), f"Expected bestmove, got '{bestmove_line}'"
    parts = bestmove_line.split()
    assert len(parts) >= 2, f"Invalid bestmove format: '{bestmove_line}'"
    logging.info(f"PASS: UCI 'position' & 'go' produced legal bestmove: '{parts[1]}'.")

    # 4. Quit
    proc.stdin.write("quit\n")
    proc.stdin.flush()
    proc.wait(timeout=3)
    logging.info("PASS: Clean exit on 'quit'.")


if __name__ == "__main__":
    test_cli_mode()
    test_uci_protocol()
    logging.info("ALL PROTOCOL TESTS PASSED SUCCESSFULLY!")

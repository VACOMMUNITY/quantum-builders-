import os
import sys

# Platform and System Hardware limits
TOTAL_CORES = os.cpu_count() or 4
# Choose a safe thread count (don't choke system, leave room for OS and input/output)
DEFAULT_THREADS = min(4, max(1, TOTAL_CORES - 2))

# Memory: default to safe 128MB hash (leaves >90% RAM free on 16GB system)
DEFAULT_HASH_MB = 32

# Search and Time Limits
DEFAULT_MOVETIME_MS = 50  # Very fast target: 50 milliseconds per move
SAFETY_MARGIN_MS = 10      # Small margin for I/O and protocol overhead
MIN_SEARCH_MS = 10         # Minimum engine search time

# Engine binary location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKFISH_BIN_PATH = os.path.join(
    BASE_DIR, "stockfish", "stockfish-windows-x86-64-universal.exe"
)

# Tournament rules flag: Can be toggled if Stockfish is explicitly prohibited
PERMIT_STOCKFISH = True

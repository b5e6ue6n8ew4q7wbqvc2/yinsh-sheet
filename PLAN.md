# Yinsh Improvement Plan

## Goals
Training-focused improvements: play vs AI, rewind/review moves, save and reload games,
and visually export games as an image sheet.

## Decisions Made
- **UI:** Mode-selection screen — Player vs Player or Player vs AI; PvP includes a Blitz mode checkbox
- **Save format:** Plain text using standard board notation (e.g. `E4`)
- **Export:** Streamlit app (`app.py`) reads a BGA log or native save file and
  produces a PNG image sheet — **done and deployed**
- **Rewind:** Available both during AND after the game
- **Undo:** View-only — rewind doesn't branch the game; "Resume Live" jumps back to the current live position
- **Web build:** Emscripten/WebAssembly, hosted on itch.io

---

## Part A — C++ Game Changes ✅ DONE

### Phase 0 — Board Labels ✅
- Draw column letters **A–K** and row numbers **1–11** around the board edges using raylib's text rendering
- Labels drawn in world space, scaled by `camera.zoom` so they remain a fixed pixel size
- White colour, offset just outside the outermost valid node of each line

### Phase 1 — Streamline UI ✅
- Initial `ChoosingMode` screen: "Player vs Player" (with Blitz checkbox) or "Player vs AI"
- PvP goes directly to `Playing`; AI path leads to the settings screen (color pick, time, memory, threads)
- "Load Game" button on both screens to enter review mode from a saved file

### Phase 2 — Move History ✅
- `std::vector<Yngine::Move> move_history` added to `Game`
- `size_t review_cursor` (equals `move_history.size()` when at the live position)
- `BoardState replay_board` re-derived by replaying all moves from scratch up to `review_cursor`
- `Game::State::Reviewing` — shows the replayed board, pauses AI input (but does not cancel any running search future)

### Phase 3 — Review UI Controls ✅
- Compact rounded panel in the top-left corner, visible during `Playing` and `Reviewing`
- Row 1: `|<` jump to start, `<` one move back, `Move N / M` counter, `>` one move forward, `>|` jump to end
- Row 2: "Resume Live" button (disabled when already at live position)
- Row 3: "Save" button (disabled when no moves made)
    - Row 4: "New Game" button — resets all state and returns to the mode-selection screen
- Navigation buttons disabled (greyed) rather than hidden when not applicable

### Phase 4 — Save Game ✅
- Auto-save to `YYYYMMDD_HHMMSS.txt` when game reaches GameOver (once per game)
- "Save" button in the review panel to save manually at any time
- File format: see **Save Format Spec** below

### Phase 5 — Load Game ✅
- Parse the plain-text format, reconstruct `move_history`, enter `Reviewing` state at move 0
- Validate each move against a replayed `BoardState` during loading; report parse errors to stderr
- Settings screen: "Load Game" button expands to a text box + Load/Cancel buttons; shows error on failure

### New Game Button ✅
- "New Game" in the review panel resets board, history, engine, and returns to the settings screen

---

## Upstream Contribution ✅ PR Open

All C++ game changes have been contributed back to the upstream project via a pull request.

- **PR**: https://github.com/temhelk/yinsh/pull/2
- **Branch**: `feature/review-save-blitz-pvp` in fork `b5e6ue6n8ew4q7wbqvc2/yinsh`
- **Targets**: `temhelk/blitz` (builds on top of their existing blitz branch)
- **Remotes in this repo**: `temhelk` → upstream, `myfork` → `b5e6ue6n8ew4q7wbqvc2/yinsh`

---

## Part B — Python Image Sheet Tool ✅ DONE

Streamlit app at `app.py`, repo: `github.com/b5e6ue6n8ew4q7wbqvc2/yinsh-sheet`

### What it does
- Auto-detects input format (BGA play log or native save file)
- Parses BGA play logs (auto-handles `takes back their last move`, multi-step undos)
- Parses native save files (PLACE/MOVE/REMOVE_ROW/REMOVE_RING, derives colour from turn sequence)
- Replays the full game in pure Python
- Renders each board position as an upright hex grid (nodes-and-lines, matches the physical board)
- Highlights: red = last-moved ring positions, orange = markers flipped this move
- Lays out all positions as a bordered PNG sheet with captions
- Title bar: `White (2) vs Black (3)   |   4/9/2026 – 4/10/2026   |   Black wins`
- Download filename: `20260409_White_vs_Black.png`

---

## Web Build

The game is built for the web using Emscripten and hosted on itch.io as an HTML5 game.

### Building
```bash
# Configure (once)
nix-shell -p emscripten cmake ninja python3 --run "
  EM_CACHE=/home/bob/.emscripten_cache \
  emcmake cmake -S . -B build-web -DCMAKE_BUILD_TYPE=Release -DPLATFORM=Web -GNinja
"

# Build
nix-shell -p emscripten cmake ninja python3 --run "
  EM_CACHE=/home/bob/.emscripten_cache cmake --build build-web
"
```

### Packaging for itch.io
```bash
cd build-web/yinsh-gui
cp Yinsh-gui.html index.html
zip ~/yinsh-web.zip index.html Yinsh-gui.js Yinsh-gui.wasm
```

Upload `yinsh-web.zip` to itch.io as an HTML5 game with **SharedArrayBuffer support** enabled
(required for pthreads / AI search).

### Native build (for local testing)
```bash
nix-shell -p cmake ninja gcc xorg.libX11 xorg.libXrandr xorg.libXinerama \
          xorg.libXcursor xorg.libXi xorg.libXext libGL --run "
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -GNinja && cmake --build build
"
# Binary: build/yinsh-gui/Yinsh-gui
```

---

## Save Format Spec

Plain text, one record per line, readable by both the C++ loader and the Python app.

```
# DATE 20260409_143022          (YYYYMMDD_HHMMSS of game end)
# PLAYER_COLOR White             (color the human played: White or Black)
# RESULT White|Black|Draw|Unfinished
PLACE E4
MOVE E4 E9
REMOVE_ROW E5 E9
REMOVE_RING D6
```

Rules:
- Lines beginning with `#` are metadata, all optional
- Move lines use uppercase `Letter+Number` coords, matching BGA notation exactly
- `MOVE` always flips markers between `from` and `to` — direction is inferred from the two coords
- `REMOVE_ROW` always covers exactly 5 cells; `from` and `to` are the two endpoints
- No `PASS` line needed (Yinsh has no pass)
- Blank lines and unknown `#` keys are ignored

---

## Coordinate System Reference

Standard Yinsh notation: `<Letter><Number>` e.g. `E4`, `K10`, `H7`

**Confirmed mapping (verified against BGA logs):**
```
letter_index = ord(letter) - ord('A')     # 0=A .. 10=K
x = (letter_index + 5) - (number - 1)
y = number - 1
engine_index = 11 * y + x
```
Inverse:
```
letter = chr(ord('A') + x + y - 5)
number = y + 1
```

**Visual orientation (upright board, matches physical Yinsh and BGA):**
```
pixel_x = (x + y - 10) * spacing          # horizontal, A=left K=right
pixel_y = (x - y) * spacing / sqrt(3)     # vertical, 1=bottom 11=top (PIL y-axis points down)
```
- Vertical lines = x=const (NE direction)
- 30° diagonals = y=const (SE direction)
- 30° diagonals = x+y=const (N direction)
- Letters A–K along the bottom, numbers 1–11 along the left edge

**Engine internals:**
- `uint8_t index = 11*y + x` (0–120)
- Valid cells bitmask: `(0x783F8FF3FEFFD << 64) | 0xFF7FEFF9FE3F83C0`
- Direction enum: SE=0 (+1,0), NE=1 (0,+1), N=2 (-1,+1), NW=3 (-1,0), SW=4 (0,-1), S=5 (+1,-1)
- `HVec2{x, y}` where x and y are in [0..10]

---

## Key Technical Notes (C++)
- **Replay from scratch:** Rewinding rebuilds `replay_board` by constructing a fresh `BoardState`
  and calling `apply_move` for each move up to the cursor. No undo method needed on `BoardState`.
- **Engine not interrupted during review:** The AI `std::future` (if running) continues in the
  background. When the user resumes live, the result is applied normally if it has arrived.
- **File I/O:** Standard `<fstream>` and `<chrono>`/`<ctime>` for timestamps. No new dependencies.
- **Dual state:** GUI `BoardState` (board.hpp) and engine `Yngine::BoardState` (board_state.hpp)
  must both be kept in sync via `apply_move` on both whenever a live move is made.
  The `replay_board` is GUI-only (no engine sync needed).
- **Save format uses standard coords:** Indices are converted to/from `Letter+Number` on
  save/load so files are human-readable and cross-compatible with BGA logs and the Python tool.
- **Web canvas sizing:** On Emscripten builds, `window.innerWidth/Height` is read via `EM_ASM_INT`
  at startup and each frame to keep the raylib canvas in sync with the itch.io iframe.

# Yinsh Improvement Plan

## Goals
Training-focused improvements: play vs AI, rewind/review moves, save and reload games,
and visually export games as an image sheet.

## Decisions Made
- **UI:** AI-only mode (remove Player vs Player)
- **Save format:** Plain text using standard board notation (e.g. `E4`)
- **Export:** Streamlit app (`app.py`) reads a BGA log or our save format and
  produces a PNG image sheet — **done and deployed**
- **Rewind:** Available both during AND after the game
- **Undo:** View-only — rewind doesn't branch the game; "Resume Live" jumps back to the current live position

---

## Part A — C++ Game Changes

### Phase 0 — Board Labels
- Draw column letters **A–K** and row numbers **1–11** around the board edges using raylib's text rendering
- Coordinate mapping (confirmed against BGA logs and engine internals):
  - `letter → x + y = ord(letter) - ord('A') + 5`
  - `number → y = number - 1`
  - Therefore: `x = (ord(letter) - ord('A') + 5) - (number - 1)`
  - Engine index: `11 * y + x`
- BGA uses uppercase; match that convention

### Phase 1 — Streamline UI
- Remove "Player vs Player" mode and the `ChoosingMode` state entirely
- First screen becomes the AI settings screen directly (color pick, time, memory, threads)
- Add a "Load Game" button on the settings screen to enter review mode from a saved file

### Phase 2 — Move History
- Add `std::vector<Yngine::Move> move_history` to `Game`
- Track `size_t review_cursor` (equals `move_history.size()` when at the live position)
- Add a `BoardState replay_board` re-derived by replaying all moves from scratch up to `review_cursor` whenever the cursor changes (fast: <100 moves, pure array ops)
- New `Game::State::Reviewing` — shows the replayed board, pauses AI input (but does not cancel any running search future)

### Phase 3 — Review UI Controls
- Draw a semi-transparent overlay bar at the bottom of the board during `Playing` and `Reviewing` states:
  - `◀◀` jump to start, `◀` one move back, `▶` one move forward, `▶▶` jump to end/live
  - "Resume Live" button (only visible when `review_cursor < move_history.size()`)
  - Move counter label: e.g. `Move 14 / 22`
- Clicking any navigation button sets `state = Reviewing` and updates `review_cursor`
- "Resume Live" sets `review_cursor = move_history.size()` and returns to `Playing`

### Phase 4 — Save Game
- Auto-save to `YYYYMMDD_HHMMSS.txt` when game reaches GameOver
- "Save" button in the review bar to save manually at any time
- File format (see **Save Format Spec** below)

### Phase 5 — Load Game
- Parse the plain-text format, reconstruct `move_history`, enter `Reviewing` state at move 0
- Validate each move against a replayed `BoardState` during loading; report parse errors to stderr

---

## Part B — Python Image Sheet Tool ✅ DONE

Streamlit app at `app.py`, repo: `github.com/b5e6ue6n8ew4q7wbqvc2/yinsh-sheet`

### What it does
- Parses BGA play logs (auto-handles `takes back their last move`, multi-step undos)
- Replays the full game in pure Python
- Renders each board position as an upright hex grid (nodes-and-lines, matches the physical board)
- Highlights: red = last-moved ring positions, orange = markers flipped this move
- Lays out all positions as a bordered PNG sheet with captions
- Title bar: `White (2) vs Black (3)   |   4/9/2026 – 4/10/2026   |   Black wins`
- Download filename: `20260409_White_vs_Black.png`

### Still to add (future)
- Support for our native save format (Part A Phase 4) as a second input — see Save Format Spec below

---

## Save Format Spec

Plain text, one record per line, designed to be parseable by both the C++ loader and
the Python Streamlit app.  **Must be supported by `app.py` as a second input format.**

```
# DATE 20260409_143022          (YYYYMMDD_HHMMSS of game start)
# PLAYER_COLOR White             (color the human played: White or Black)
# WHITE_PLAYER HardDiggler       (display name — omit if unknown)
# BLACK_PLAYER yngine_ai         (display name — omit if unknown)
# MOVE_TIME 5                    (AI move time in seconds)
# RESULT White|Black|Draw|Unfinished
PLACE E4
MOVE E4 E9
REMOVE_ROW E5 E9
REMOVE_RING D6
```

Rules:
- Lines beginning with `#` are metadata, all optional except `DATE` and `RESULT`
- Move lines use uppercase `Letter+Number` coords, matching BGA notation exactly
- `MOVE` always flips markers between `from` and `to` — direction is inferred from the two coords
- `REMOVE_ROW` always covers exactly 5 cells; `from` and `to` are the two endpoints
- No `PASS` line needed (Yinsh has no pass)
- Blank lines and unknown `#` keys are ignored

### Parser additions needed in `app.py`
When the input does **not** contain `Move N :` BGA headers, treat it as native format:
- Read `#` metadata into `player_map` and `metadata`
- `PLACE coord` → `PlaceRing`
- `MOVE from to` → `MoveRing` (marker placement is implicit, same as BGA handling)
- `REMOVE_ROW from to` → `RemoveRow`
- `REMOVE_RING coord` → `RemoveRing`
- No takeback handling needed (save file only stores confirmed moves)

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
- **Log output for the Streamlit app:** When writing the save file, the C++ code can optionally
  also write a BGA-compatible log (or just use the native format above — the app will support both).
  The native format is simpler to write from C++ and avoids duplicating player-name/timestamp logic.

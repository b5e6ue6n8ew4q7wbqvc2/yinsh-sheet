"""
Yinsh Game Sheet Renderer
Streamlit app that parses a BGA play log (or native save format) and renders
every board position as a small hex-grid image, laid out as a single PNG sheet.

Coordinate mapping (derived from engine internals):
  BGA notation:  <Letter><Number>  e.g. E4, K10
  Engine (x, y): x = (ord(letter) - ord('A') + 5) - (number - 1)
                 y = number - 1
  Index:         11 * y + x
  Constraint:    x + y = ord(letter) - ord('A') + 5
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from typing import Optional

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOARD_BITS = (0x783F8FF3FEFFD << 64) | 0xFF7FEFF9FE3F83C0
VALID_CELLS: set[tuple[int, int]] = set()
for _y in range(11):
    for _x in range(11):
        if BOARD_BITS & (1 << (11 * _y + _x)):
            VALID_CELLS.add((_x, _y))

# Six hex directions matching the engine:  SE NE N NW SW S
DIRECTIONS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]

# Colors used in rendering — match the C++ game (bg is 0xB7B3AFFF)
BOARD_BG        = "#B7B3AF"
LINE_COLOR      = "#383838"
NODE_DOT_COLOR  = "#383838"
WHITE_COLOR     = "#FFFFFF"
BLACK_COLOR     = "#1A1A1A"
HIGHLIGHT_COLOR = "#DD2222"   # red: last-moved ring positions
FLIP_COLOR      = "#FF8800"   # orange: markers flipped this move

# Board line extents — from board.hpp BOARD_START_OFFSET / BOARD_END_OFFSET
# Index is x (for x-const lines) or y (for y-const lines)
BOARD_START_OFFSET = [6, 4, 3, 2, 1, 1, 0, 0, 0, 0, 1]
BOARD_END_OFFSET   = [9, 10, 10, 10, 10, 9, 9, 8, 7, 6, 4]

# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def bga_to_xy(coord: str) -> tuple[int, int]:
    """Convert BGA notation like 'E4' or 'K10' to engine (x, y)."""
    coord = coord.strip().upper()
    letter = coord[0]
    number = int(coord[1:])
    li = ord(letter) - ord("A")
    y = number - 1
    x = (li + 5) - y
    return x, y

def xy_to_bga(x: int, y: int) -> str:
    letter = chr(ord("A") + (x + y - 5))
    number = y + 1
    return f"{letter}{number}"

def xy_valid(x: int, y: int) -> bool:
    return (x, y) in VALID_CELLS

# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

class Color:
    WHITE = "white"
    BLACK = "black"

    @staticmethod
    def opposite(c: str) -> str:
        return Color.BLACK if c == Color.WHITE else Color.WHITE


@dataclass
class BoardState:
    """Pure-Python board state.  Mirrors the engine logic but without bitboards."""

    white_rings:   set[tuple[int, int]] = field(default_factory=set)
    black_rings:   set[tuple[int, int]] = field(default_factory=set)
    white_markers: set[tuple[int, int]] = field(default_factory=set)
    black_markers: set[tuple[int, int]] = field(default_factory=set)

    # whose turn it is to place/move a ring
    turn: str = Color.WHITE   # WHITE places first in Yinsh

    # how many rings each player has placed (placement phase)
    rings_placed: int = 0

    def copy(self) -> "BoardState":
        return BoardState(
            white_rings=set(self.white_rings),
            black_rings=set(self.black_rings),
            white_markers=set(self.white_markers),
            black_markers=set(self.black_markers),
            turn=self.turn,
            rings_placed=self.rings_placed,
        )

    # --- placement phase ---

    def place_ring(self, xy: tuple[int, int], color: str) -> None:
        if color == Color.WHITE:
            self.white_rings.add(xy)
        else:
            self.black_rings.add(xy)
        self.rings_placed += 1
        self.turn = Color.opposite(color)

    # --- move phase ---

    def move_ring(self, frm: tuple[int, int], to: tuple[int, int], color: str) -> set[tuple[int, int]]:
        """Apply a ring move: leave marker at frm, flip markers on the way, place ring at to.
        Returns the set of cells whose markers were flipped."""
        rings = self.white_rings if color == Color.WHITE else self.black_rings
        markers_own = self.white_markers if color == Color.WHITE else self.black_markers
        markers_opp = self.black_markers if color == Color.WHITE else self.white_markers

        assert frm in rings, f"{color} ring not at {xy_to_bga(*frm)} (engine {frm})"
        rings.discard(frm)
        rings.add(to)

        # place marker at frm
        markers_own.add(frm)

        # flip markers strictly between frm and to
        between = self._cells_between(frm, to)
        flipped: set[tuple[int, int]] = set()
        for cell in between:
            if cell in markers_own:
                markers_own.discard(cell)
                markers_opp.add(cell)
                flipped.add(cell)
            elif cell in markers_opp:
                markers_opp.discard(cell)
                markers_own.add(cell)
                flipped.add(cell)

        self.turn = Color.opposite(color)
        return flipped

    @staticmethod
    def _cells_between(frm: tuple[int, int], to: tuple[int, int]) -> list[tuple[int, int]]:
        """Return all cells strictly between frm and to along a straight hex line."""
        dx = to[0] - frm[0]
        dy = to[1] - frm[1]
        # Determine unit step
        length = max(abs(dx), abs(dy), abs(dx - dy)) if dx != dy else abs(dx)
        if length == 0:
            return []
        # Normalise — should be a straight line so gcd divides both
        g = math.gcd(abs(dx), abs(dy)) if (dx != 0 and dy != 0) else max(abs(dx), abs(dy))
        ux, uy = dx // g, dy // g
        cells = []
        cx, cy = frm[0] + ux, frm[1] + uy
        while (cx, cy) != to:
            cells.append((cx, cy))
            cx += ux
            cy += uy
        return cells

    def remove_row(self, frm: tuple[int, int], to: tuple[int, int], color: str) -> None:
        """Remove 5 markers in a row from frm to to (inclusive)."""
        markers = self.white_markers if color == Color.WHITE else self.black_markers
        cells = [frm] + self._cells_between(frm, to) + [to]
        assert len(cells) == 5, f"Row has {len(cells)} cells, expected 5: {cells}"
        for cell in cells:
            markers.discard(cell)

    def remove_ring(self, xy: tuple[int, int], color: str) -> None:
        rings = self.white_rings if color == Color.WHITE else self.black_rings
        rings.discard(xy)

    def all_pieces(self) -> set[tuple[int, int]]:
        return (self.white_rings | self.black_rings |
                self.white_markers | self.black_markers)


# ---------------------------------------------------------------------------
# Move dataclasses (parsed representation)
# ---------------------------------------------------------------------------

@dataclass
class PlaceRing:
    coord: tuple[int, int]
    color: str

@dataclass
class MoveRing:
    frm: tuple[int, int]
    to: tuple[int, int]
    color: str

@dataclass
class RemoveRow:
    frm: tuple[int, int]
    to: tuple[int, int]
    color: str

@dataclass
class RemoveRing:
    coord: tuple[int, int]
    color: str

@dataclass
class _PlaceMarker:
    """Internal sentinel — BGA logs marker placement as a separate undoable step.
    Stripped from the move list before replay; move_ring() places the marker implicitly."""
    coord: tuple[int, int]
    color: str

Move = PlaceRing | MoveRing | RemoveRow | RemoveRing | _PlaceMarker


# ---------------------------------------------------------------------------
# BGA log parser
# ---------------------------------------------------------------------------

_COORD_RE = re.compile(r"\b([A-K]\d{1,2})\b")
_MOVE_HDR = re.compile(r"^Move\s+\d+\s*:", re.IGNORECASE)
_PLACE_RING   = re.compile(r"places a ring on ([A-K]\d{1,2})", re.IGNORECASE)
_PLACE_MARKER = re.compile(r"places a marker on ([A-K]\d{1,2})", re.IGNORECASE)
_MOVE_RING    = re.compile(r"moves a ring from ([A-K]\d{1,2}) to ([A-K]\d{1,2})", re.IGNORECASE)
_TAKES_BACK   = re.compile(r"takes back their last move", re.IGNORECASE)
_RESTARTS     = re.compile(r"restarts their turn", re.IGNORECASE)
_REMOVE_ROW   = re.compile(r"removes? (?:a )?row (?:of markers )?from ([A-K]\d{1,2}) to ([A-K]\d{1,2})", re.IGNORECASE)
_REMOVE_RING  = re.compile(r"removes? (?:a )?ring (?:from|on|at) ([A-K]\d{1,2})", re.IGNORECASE)


def _name_to_color(name: str, player_map: dict[str, str]) -> str:
    """Look up a player name and return their color, registering if first seen."""
    if name not in player_map:
        if len(player_map) == 0:
            player_map[name] = Color.WHITE
        else:
            player_map[name] = Color.BLACK
    return player_map[name]


@dataclass
class ParsedGame:
    moves: list[Move]
    player_map: dict[str, str]   # name -> color
    metadata: dict[str, str]


_DATE_IN_HEADER = re.compile(r"Move\s+\d+\s*:\s*(\d+/\d+/\d+)", re.IGNORECASE)


def parse_bga_log(text: str) -> ParsedGame:
    """
    Parse a BGA Yinsh play log into a list of Move objects.

    BGA logs each game-move as 2 lines: "places a marker on X" then "moves a ring from X to Y".
    BGA also logs RemoveRow and RemoveRing as separate lines.
    Each of these BGA lines is one undoable step, so we keep them all separate in the moves list.

    'takes back their last move' pops the most recently added move.
    """
    lines = text.strip().splitlines()
    player_map: dict[str, str] = {}
    metadata: dict[str, str] = {}
    moves: list[Move] = []

    # Track first and last date seen in Move headers
    first_date: Optional[str] = None
    last_date:  Optional[str] = None

    _IGNORE = re.compile(
        r"has removed \d+ ring|End of game|^Move\s+\d+\s*:",
        re.IGNORECASE
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _MOVE_HDR.match(line):
            dm = _DATE_IN_HEADER.match(line)
            if dm:
                d = dm.group(1)
                if first_date is None:
                    first_date = d
                last_date = d
            continue

        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        player_name, rest = parts[0], parts[1]

        # Skip informational lines
        if _IGNORE.search(rest) or _IGNORE.search(line):
            continue

        if _TAKES_BACK.search(rest):
            if moves:
                moves.pop()
            continue

        if _RESTARTS.search(rest):
            # Undo the entire current turn: pop back through and including the
            # _PlaceMarker that started this turn (MoveRing, optional RemoveRow/
            # RemoveRing actions, then the _PlaceMarker itself).
            while moves and not isinstance(moves[-1], _PlaceMarker):
                moves.pop()
            if moves:
                moves.pop()  # pop the _PlaceMarker itself
            continue

        m = _PLACE_RING.search(rest)
        if m:
            coord = bga_to_xy(m.group(1))
            color = _name_to_color(player_name, player_map)
            moves.append(PlaceRing(coord=coord, color=color))
            continue

        m = _PLACE_MARKER.search(rest)
        if m:
            # Marker placement is a separate undoable step — store it.
            # At replay time, move_ring() will place the marker automatically,
            # so we just track this as a no-op sentinel by storing it as a
            # PlaceRing with color info (we use a dedicated type below).
            coord = bga_to_xy(m.group(1))
            color = _name_to_color(player_name, player_map)
            moves.append(_PlaceMarker(coord=coord, color=color))
            continue

        m = _MOVE_RING.search(rest)
        if m:
            frm = bga_to_xy(m.group(1))
            to  = bga_to_xy(m.group(2))
            color = _name_to_color(player_name, player_map)
            moves.append(MoveRing(frm=frm, to=to, color=color))
            continue

        m = _REMOVE_ROW.search(rest)
        if m:
            frm = bga_to_xy(m.group(1))
            to  = bga_to_xy(m.group(2))
            color = _name_to_color(player_name, player_map)
            moves.append(RemoveRow(frm=frm, to=to, color=color))
            continue

        m = _REMOVE_RING.search(rest)
        if m:
            coord = bga_to_xy(m.group(1))
            color = _name_to_color(player_name, player_map)
            moves.append(RemoveRing(coord=coord, color=color))
            continue

    # Strip _PlaceMarker sentinels — move_ring() places the marker implicitly
    moves = [m for m in moves if not isinstance(m, _PlaceMarker)]

    if first_date:
        metadata["first_date"] = first_date
    if last_date:
        metadata["last_date"] = last_date

    return ParsedGame(moves=moves, player_map=player_map, metadata=metadata)


# ---------------------------------------------------------------------------
# Native save-format parser  (C++ game output)
# ---------------------------------------------------------------------------
#
# Format (one record per line):
#   # DATE 20260409_143022
#   # PLAYER_COLOR White
#   # RESULT White|Black|Draw|Unfinished
#   PLACE E4
#   MOVE E4 E9
#   REMOVE_ROW E5 E9
#   REMOVE_RING D6
#
# Colour is NOT stored per-move; we track it ourselves by replaying the
# game-state turn sequence (white places first, then alternates).

def parse_native_log(text: str) -> ParsedGame:
    """Parse a native C++ save file into a ParsedGame."""
    lines = text.strip().splitlines()
    metadata: dict[str, str] = {}
    player_map: dict[str, str] = {}

    # Collect metadata from # comments
    for line in lines:
        line = line.strip()
        if not line.startswith("#"):
            continue
        parts = line[1:].strip().split(None, 1)
        if len(parts) == 2:
            metadata[parts[0].upper()] = parts[1].strip()

    # Build player_map from PLAYER_COLOR + fixed names "White" / "Black"
    player_map["White"] = Color.WHITE
    player_map["Black"] = Color.BLACK

    # We need to track whose turn it is to assign colour to each move.
    # Mirror the engine's NextAction state machine in miniature.
    # States: placing_rings | moving | removing_row | removing_ring
    TOTAL_RINGS = 10  # 5 per player
    rings_placed = 0
    next_action  = "place"   # place | move | remove_row | remove_ring
    turn         = Color.WHITE   # white places first

    # After a RemoveRow the same colour removes a ring, then turn flips.
    # After a RemoveRing, turn flips to the other player.
    # Multiple consecutive RemoveRow+RemoveRing sequences can happen in one
    # "move" if both players have rows (handled by the engine; in practice
    # it serialises them as separate lines so we just follow the sequence).
    pending_remove_color: str | None = None

    moves: list[Move] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        tokens = line.split()
        verb   = tokens[0].upper()

        if verb == "PLACE":
            if len(tokens) != 2:
                raise ValueError(f"Bad PLACE line: {line!r}")
            coord = bga_to_xy(tokens[1].upper())
            moves.append(PlaceRing(coord=coord, color=turn))
            rings_placed += 1
            turn = Color.opposite(turn)
            if rings_placed >= TOTAL_RINGS:
                next_action = "move"

        elif verb == "MOVE":
            if len(tokens) != 3:
                raise ValueError(f"Bad MOVE line: {line!r}")
            frm = bga_to_xy(tokens[1].upper())
            to  = bga_to_xy(tokens[2].upper())
            moves.append(MoveRing(frm=frm, to=to, color=turn))
            # After a ring move, next could be remove_row or the opponent moves
            # We'll handle the turn flip after remove_row/ring or immediately
            pending_remove_color = turn   # in case rows need removing
            next_action = "remove_row_or_move"
            turn = Color.opposite(turn)   # tentatively flip; remove_row overrides

        elif verb == "REMOVE_ROW":
            if len(tokens) != 3:
                raise ValueError(f"Bad REMOVE_ROW line: {line!r}")
            frm = bga_to_xy(tokens[1].upper())
            to  = bga_to_xy(tokens[2].upper())
            # The player who just moved (pending_remove_color) removes the row
            color = pending_remove_color if pending_remove_color is not None else Color.opposite(turn)
            moves.append(RemoveRow(frm=frm, to=to, color=color))
            # Turn stays on remove_ring for same player

        elif verb == "REMOVE_RING":
            if len(tokens) != 2:
                raise ValueError(f"Bad REMOVE_RING line: {line!r}")
            coord = bga_to_xy(tokens[1].upper())
            color = pending_remove_color if pending_remove_color is not None else Color.opposite(turn)
            moves.append(RemoveRing(coord=coord, color=color))
            # After removing a ring, pending_remove_color resets; next line
            # may be another REMOVE_ROW (other player also had a row) or a MOVE
            pending_remove_color = None

        else:
            raise ValueError(f"Unknown verb: {verb!r}")

    return ParsedGame(moves=moves, player_map=player_map, metadata=metadata)


def is_native_format(text: str) -> bool:
    """Return True if the text looks like a native C++ save file."""
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        verb = tokens[0].upper()
        # BGA logs start with "Move N :" headers or "PlayerName verb …"
        # Native verbs are PLACE, MOVE (exactly 3 tokens), REMOVE_ROW, REMOVE_RING
        if verb == "PLACE" and len(tokens) == 2:
            return True
        if verb == "MOVE" and len(tokens) == 3:
            return True
        if verb == "REMOVE_ROW" and len(tokens) == 3:
            return True
        if verb == "REMOVE_RING" and len(tokens) == 2:
            return True
        return False
    return False


def parse_log(text: str) -> ParsedGame:
    """Auto-detect format and parse."""
    if is_native_format(text):
        return parse_native_log(text)
    return parse_bga_log(text)


# ---------------------------------------------------------------------------
# Game replay
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    """A rendered snapshot: the board state plus which cells to highlight."""
    board: BoardState
    highlight: set[tuple[int, int]]   # red: moved ring positions
    flipped: set[tuple[int, int]]     # orange: markers flipped this move
    move_index: int   # 1-based move number shown in caption
    label: str        # short description e.g. "White places ring at E4"


@dataclass
class GameResult:
    white_rings: int   # rings removed by white (= white's score)
    black_rings: int   # rings removed by black
    winner: str        # Color.WHITE / Color.BLACK / "draw" / ""


def replay_game(parsed: ParsedGame) -> tuple[list[Frame], GameResult]:
    """Replay all moves, capturing a Frame after every move.
    Returns (frames, result)."""
    board = BoardState()
    frames: list[Frame] = []
    white_rings_removed = 0
    black_rings_removed = 0

    # Initial empty board
    frames.append(Frame(
        board=board.copy(),
        highlight=set(),
        flipped=set(),
        move_index=0,
        label="Start",
    ))

    for i, move in enumerate(parsed.moves, start=1):
        highlight: set[tuple[int, int]] = set()
        flipped:   set[tuple[int, int]] = set()

        if isinstance(move, PlaceRing):
            board.place_ring(move.coord, move.color)
            highlight.add(move.coord)
            label = f"{move.color.capitalize()} places ring at {xy_to_bga(*move.coord)}"

        elif isinstance(move, MoveRing):
            flipped = board.move_ring(move.frm, move.to, move.color)
            highlight.add(move.frm)   # marker left behind
            highlight.add(move.to)    # ring's new position
            label = (f"{move.color.capitalize()} moves ring "
                     f"{xy_to_bga(*move.frm)} → {xy_to_bga(*move.to)}")

        elif isinstance(move, RemoveRow):
            board.remove_row(move.frm, move.to, move.color)
            cells = ([move.frm]
                     + BoardState._cells_between(move.frm, move.to)
                     + [move.to])
            highlight.update(cells)
            label = (f"{move.color.capitalize()} removes row "
                     f"{xy_to_bga(*move.frm)}–{xy_to_bga(*move.to)}")

        elif isinstance(move, RemoveRing):
            board.remove_ring(move.coord, move.color)
            highlight.add(move.coord)
            label = f"{move.color.capitalize()} removes ring at {xy_to_bga(*move.coord)}"
            if move.color == Color.WHITE:
                white_rings_removed += 1
            else:
                black_rings_removed += 1

        else:
            label = "Unknown move"

        frames.append(Frame(
            board=board.copy(),
            highlight=highlight,
            flipped=flipped,
            move_index=i,
            label=label,
        ))

    if white_rings_removed > black_rings_removed:
        winner = Color.WHITE
    elif black_rings_removed > white_rings_removed:
        winner = Color.BLACK
    elif white_rings_removed > 0:
        winner = "draw"
    else:
        winner = ""

    result = GameResult(
        white_rings=white_rings_removed,
        black_rings=black_rings_removed,
        winner=winner,
    )
    return frames, result


# ---------------------------------------------------------------------------
# Hex board renderer — nodes-and-lines style, upright orientation
# ---------------------------------------------------------------------------
#
# Coordinate formula derived from the official YINSH board SVG (Wikimedia):
#   pixel_x = (x + y - 10) * spacing    + center_x
#   pixel_y = (x - y)      * spacing/2  + center_y
#
# This produces the canonical upright board:
#   - Vertical lines (engine NE direction, x fixed)
#   - Letters A-K along the bottom, A at left, K at right
#   - Numbers 1-11 along the left diagonal edge
#   - spacing = horizontal distance between adjacent diagonal columns

SQRT3 = math.sqrt(3)


def _node_pos(x: int, y: int, spacing: float) -> tuple[float, float]:
    """Pixel position of node (x, y).
    spacing: horizontal distance between adjacent diagonal columns (= 25*sqrt(3) per unit).
    Origin is at the board centre (x=5, y=5).
    """
    px = (x + y - 10) * spacing
    py = (x - y) * spacing / SQRT3
    return px, py


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def render_board(frame: Frame, spacing: int = 28) -> Image.Image:
    """
    Render a single board position as a PIL Image.
    spacing: pixels between adjacent nodes.
    """
    board     = frame.board
    highlight = frame.highlight

    # --- compute node pixel positions ---
    nodes: dict[tuple[int, int], tuple[float, float]] = {
        (x, y): _node_pos(x, y, spacing) for (x, y) in VALID_CELLS
    }

    xs = [p[0] for p in nodes.values()]
    ys = [p[1] for p in nodes.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Padding: row numbers left only, column letters below only.
    # Add matching right/top margins so the board grid is visually centred.
    margin         = int(spacing * 0.6)   # small gap on all sides
    label_pad_left = int(spacing * 1.5)   # extra for row number labels
    label_pad_bot  = int(spacing * 1.2)   # extra for column letter labels

    # Mirror the label pads on the opposite sides so the grid is centred
    ox = -min_x + margin + label_pad_left
    oy = -min_y + margin

    img_w = int(max_x - min_x + 2 * margin + label_pad_left + label_pad_left)
    img_h = int(max_y - min_y + 2 * margin + label_pad_bot)

    img  = Image.new("RGB", (img_w, img_h), BOARD_BG)
    draw = ImageDraw.Draw(img)

    line_w = max(1, spacing // 18)

    # --- draw lines along all 3 axis families ---

    # Family 1: x = const — vertical lines in the upright board (NE direction)
    for x in range(11):
        col = [(x, y) for y in range(11) if (x, y) in VALID_CELLS]
        if len(col) < 2:
            continue
        col.sort(key=lambda p: p[1])
        px0, py0 = _node_pos(*col[0],  spacing)
        px1, py1 = _node_pos(*col[-1], spacing)
        draw.line([(px0 + ox, py0 + oy), (px1 + ox, py1 + oy)],
                  fill=LINE_COLOR, width=line_w)

    # Family 2: y = const — SE diagonal lines (bottom-left to top-right at 30°)
    for y in range(11):
        row = [(x, y) for x in range(11) if (x, y) in VALID_CELLS]
        if len(row) < 2:
            continue
        row.sort(key=lambda p: p[0])
        px0, py0 = _node_pos(*row[0],  spacing)
        px1, py1 = _node_pos(*row[-1], spacing)
        draw.line([(px0 + ox, py0 + oy), (px1 + ox, py1 + oy)],
                  fill=LINE_COLOR, width=line_w)

    # Family 3: x+y = const — N diagonal lines (bottom-right to top-left at 30°)
    for d in range(5, 16):
        diag = [(x, y) for (x, y) in VALID_CELLS if x + y == d]
        if len(diag) < 2:
            continue
        diag.sort(key=lambda p: p[0])
        px0, py0 = _node_pos(*diag[0],  spacing)
        px1, py1 = _node_pos(*diag[-1], spacing)
        draw.line([(px0 + ox, py0 + oy), (px1 + ox, py1 + oy)],
                  fill=LINE_COLOR, width=line_w)

    # --- draw empty node dots ---
    dot_r = max(1, spacing // 10)
    for (x, y), (px, py) in nodes.items():
        cx, cy = px + ox, py + oy
        draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                     fill=NODE_DOT_COLOR)

    # --- draw pieces ---
    ring_outer = spacing * 0.38
    ring_inner = spacing * 0.22
    marker_r   = spacing * 0.25
    flip_lw    = max(2, int(spacing * 0.12))   # orange outline width for flipped markers

    for (x, y), (px, py) in nodes.items():
        cx, cy   = px + ox, py + oy
        is_hi    = (x, y) in highlight
        is_flip  = (x, y) in frame.flipped

        if (x, y) in board.white_rings:
            _draw_ring(draw, cx, cy, ring_outer, ring_inner,
                       WHITE_COLOR, BLACK_COLOR, HIGHLIGHT_COLOR if is_hi else None)

        elif (x, y) in board.black_rings:
            _draw_ring(draw, cx, cy, ring_outer, ring_inner,
                       BLACK_COLOR, BLACK_COLOR, HIGHLIGHT_COLOR if is_hi else None)

        elif (x, y) in board.white_markers:
            fill    = HIGHLIGHT_COLOR if is_hi else WHITE_COLOR
            outline = FLIP_COLOR if is_flip else BLACK_COLOR
            lw      = flip_lw if is_flip else max(1, line_w)
            draw.ellipse([cx - marker_r, cy - marker_r,
                          cx + marker_r, cy + marker_r],
                         fill=fill, outline=outline, width=lw)

        elif (x, y) in board.black_markers:
            fill    = HIGHLIGHT_COLOR if is_hi else BLACK_COLOR
            outline = FLIP_COLOR if is_flip else BLACK_COLOR
            lw      = flip_lw if is_flip else max(1, line_w)
            draw.ellipse([cx - marker_r, cy - marker_r,
                          cx + marker_r, cy + marker_r],
                         fill=fill, outline=outline, width=lw)

    # --- coordinate labels ---
    font_sz    = max(7, spacing // 2)
    font_label = _load_font(font_sz)
    label_col  = "#444444"

    # Letters A–K: below the bottommost node of each x+y diagonal
    for d in range(5, 16):
        diag = [(x, y) for (x, y) in VALID_CELLS if x + y == d]
        if not diag:
            continue
        bottom = max(diag, key=lambda p: nodes[p][1])
        px, py = nodes[bottom]
        letter = chr(ord("A") + d - 5)
        draw.text((px + ox, py + oy + spacing * 0.85), letter,
                  fill=label_col, font=font_label, anchor="mm")

    # Numbers 1–11: left of the leftmost node in each engine-y row
    for y in range(11):
        row_nodes = [(x, y) for x in range(11) if (x, y) in VALID_CELLS]
        if not row_nodes:
            continue
        leftmost = min(row_nodes, key=lambda p: nodes[p][0])
        px, py = nodes[leftmost]
        draw.text((px + ox - spacing * 0.85, py + oy), str(y + 1),
                  fill=label_col, font=font_label, anchor="mm")

    return img


def _draw_ring(draw: ImageDraw.ImageDraw,
               cx: float, cy: float,
               outer_r: float, inner_r: float,
               fill: str, stroke: str,
               highlight: Optional[str]) -> None:
    """Draw a ring (annulus) centered at (cx, cy)."""
    outer = [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r]
    inner = [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r]
    draw.ellipse(outer, fill=fill, outline=stroke, width=max(1, int(outer_r * 0.12)))
    draw.ellipse(inner, fill=BOARD_BG)
    if highlight:
        lw = max(2, int(outer_r * 0.18))
        draw.ellipse(outer, fill=None, outline=highlight, width=lw)


# ---------------------------------------------------------------------------
# Sheet layout
# ---------------------------------------------------------------------------

def build_sheet(frames: list[Frame],
                spacing: int = 22,
                cols: Optional[int] = None,
                caption_height: int = 20,
                title: str = "") -> Image.Image:
    """Render all frames and tile them into a single PNG sheet."""
    if not frames:
        raise ValueError("No frames to render")

    board_imgs = [render_board(f, spacing=spacing) for f in frames]
    bw, bh = board_imgs[0].size

    n = len(board_imgs)
    if cols is None:
        cols = math.ceil(math.sqrt(n * bw / bh))
        cols = max(1, min(cols, n))
    rows = math.ceil(n / cols)

    border       = 2
    cell_w       = bw + border * 2
    cell_h       = bh + caption_height + border * 2
    gap          = 4
    title_height = 80 if title else 0
    sheet_w      = cols * cell_w + (cols - 1) * gap + gap * 2
    sheet_h      = rows * cell_h + (rows - 1) * gap + gap * 2 + title_height

    sheet = Image.new("RGB", (sheet_w, sheet_h), BOARD_BG)
    draw  = ImageDraw.Draw(sheet)

    if title:
        title_font = _load_font(52)
        # Draw title text left-aligned at top
        draw.text(
            (gap * 2, title_height // 2),
            title, fill="#111111", font=title_font, anchor="lm",
        )
        # Thin separator line under the title
        draw.line(
            [(gap, title_height - 1), (sheet_w - gap, title_height - 1)],
            fill="#888880", width=1,
        )

    font_sz = max(8, caption_height - 4)
    font    = _load_font(font_sz)

    for idx, (img, frame) in enumerate(zip(board_imgs, frames)):
        col = idx % cols
        row = idx // cols

        # top-left of the cell (border + board + caption)
        x0 = gap + col * (cell_w + gap)
        y0 = title_height + gap + row * (cell_h + gap)

        # draw border rect
        draw.rectangle(
            [x0, y0, x0 + cell_w - 1, y0 + cell_h - 1],
            outline="#888880", width=border,
        )

        # paste board image inside the border
        sheet.paste(img, (x0 + border, y0 + border))

        # caption strip (same grey as sheet, sits flush below the board)
        cap_y0 = y0 + border + bh
        cap_y1 = y0 + cell_h - border
        draw.rectangle(
            [x0 + border, cap_y0, x0 + cell_w - border - 1, cap_y1],
            fill=BOARD_BG,
        )
        # thin separator line between board and caption
        draw.line(
            [(x0 + border, cap_y0), (x0 + cell_w - border - 1, cap_y0)],
            fill="#888880", width=1,
        )

        caption = f"#{frame.move_index}  {frame.label}"
        draw.text(
            (x0 + cell_w // 2, cap_y0 + caption_height // 2),
            caption, fill="#222222", font=font, anchor="mm",
        )

    return sheet


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Yinsh Game Sheet", layout="wide")
    st.title("Yinsh Game Sheet Renderer")
    st.markdown(
        "Paste a **Board Game Arena** play log *or* a **native save file** below, then click **Render**."
    )

    log_text = st.text_area("Game log", value="", height=300,
                            placeholder="Paste a BGA play log or native save file here…")

    with st.sidebar:
        st.header("Options")
        cell_size = st.slider("Cell size (px)", min_value=14, max_value=48, value=24, step=2)
        cols_input = st.number_input("Columns (0 = auto)", min_value=0, max_value=20,
                                     value=0, step=1)
        cols = int(cols_input) if cols_input > 0 else None
        show_start = st.checkbox("Include starting empty board", value=False)
        st.markdown("---")
        st.markdown("**Color key**")
        st.markdown("- White ring / marker = White player")
        st.markdown("- Black ring / marker = Black player")
        st.markdown("- Red highlight = last moved ring positions")
        st.markdown("- Orange outline = markers flipped this move")

    if st.button("Render", type="primary"):
        with st.spinner("Parsing and rendering…"):
            try:
                parsed = parse_log(log_text)

                if not parsed.moves:
                    st.error("No moves were parsed. Check the log format.")
                    return

                frames, result = replay_game(parsed)

                if not show_start:
                    frames = frames[1:]  # drop the empty initial board

                white_name = next((n for n, c in parsed.player_map.items() if c == Color.WHITE), "White")
                black_name = next((n for n, c in parsed.player_map.items() if c == Color.BLACK), "Black")

                # Info bar
                fmt_label = "native" if is_native_format(log_text) else "BGA"
                st.info(f"Format: {fmt_label}  |  {len(parsed.moves)} moves parsed")

                # Title: "White (2) vs Black (3)  |  date  |  result"
                # Native format: DATE is YYYYMMDD_HHMMSS; BGA: M/D/YYYY
                native = is_native_format(log_text)
                if native:
                    raw_date = parsed.metadata.get("DATE", "")
                    date_str = raw_date[:8] if raw_date else ""   # just YYYYMMDD
                else:
                    first_date = parsed.metadata.get("first_date", "")
                    last_date  = parsed.metadata.get("last_date", "")
                    date_str   = first_date if first_date == last_date else f"{first_date} – {last_date}"

                title = f"{white_name} ({result.white_rings})  vs  {black_name} ({result.black_rings})"
                if date_str:
                    title += f"   |   {date_str}"

                # Use RESULT metadata from native format if available; otherwise derive from replay
                native_result = parsed.metadata.get("RESULT", "") if native else ""
                if native_result == "White":
                    title += f"   |   {white_name} wins"
                elif native_result == "Black":
                    title += f"   |   {black_name} wins"
                elif native_result == "Draw":
                    title += "   |   Draw"
                elif native_result == "Unfinished":
                    title += "   |   Unfinished"
                elif result.winner == Color.WHITE:
                    title += f"   |   {white_name} wins"
                elif result.winner == Color.BLACK:
                    title += f"   |   {black_name} wins"
                elif result.winner == "draw":
                    title += "   |   Draw"

                sheet = build_sheet(frames, spacing=cell_size, cols=cols, title=title)

                # Display inline
                st.image(sheet, caption="Game sheet", width='stretch')

                # Download button — filename: "20260409_White_vs_Black.png"
                def _fmt_bga_date(d: str) -> str:
                    """Convert M/D/YYYY to YYYYMMDD."""
                    try:
                        m, day, y = d.split("/")
                        return f"{y}{int(m):02d}{int(day):02d}"
                    except Exception:
                        return d
                safe = lambda s: re.sub(r"[^\w]", "_", s)
                if native:
                    date_part = date_str   # already YYYYMMDD or empty
                else:
                    date_part = _fmt_bga_date(parsed.metadata.get("first_date", ""))
                file_name = f"{date_part}_{safe(white_name)}_vs_{safe(black_name)}.png"

                buf = io.BytesIO()
                sheet.save(buf, format="PNG")
                buf.seek(0)
                st.download_button(
                    label="Download PNG",
                    data=buf,
                    file_name=file_name,
                    mime="image/png",
                )

            except AssertionError as e:
                st.error(f"Game replay error: {e}")
            except Exception as e:
                st.exception(e)


if __name__ == "__main__":
    main()

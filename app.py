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
HIGHLIGHT_COLOR = "#DD2222"   # last-moved pieces

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

    def move_ring(self, frm: tuple[int, int], to: tuple[int, int], color: str) -> None:
        """Apply a ring move: leave marker at frm, flip markers on the way, place ring at to."""
        rings = self.white_rings if color == Color.WHITE else self.black_rings
        markers_own = self.white_markers if color == Color.WHITE else self.black_markers
        markers_opp = self.black_markers if color == Color.WHITE else self.white_markers

        assert frm in rings, f"{color} ring not at {frm}"
        rings.discard(frm)
        rings.add(to)

        # place marker at frm
        markers_own.add(frm)

        # flip markers strictly between frm and to
        between = self._cells_between(frm, to)
        for cell in between:
            if cell in markers_own:
                markers_own.discard(cell)
                markers_opp.add(cell)
            elif cell in markers_opp:
                markers_opp.discard(cell)
                markers_own.add(cell)

        self.turn = Color.opposite(color)

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

Move = PlaceRing | MoveRing | RemoveRow | RemoveRing


# ---------------------------------------------------------------------------
# BGA log parser
# ---------------------------------------------------------------------------

_COORD_RE = re.compile(r"\b([A-K]\d{1,2})\b")
_MOVE_HDR = re.compile(r"^Move\s+\d+\s*:", re.IGNORECASE)
_PLACE_RING   = re.compile(r"places a ring on ([A-K]\d{1,2})", re.IGNORECASE)
_PLACE_MARKER = re.compile(r"places a marker on ([A-K]\d{1,2})", re.IGNORECASE)
_MOVE_RING    = re.compile(r"moves a ring from ([A-K]\d{1,2}) to ([A-K]\d{1,2})", re.IGNORECASE)
_TAKES_BACK   = re.compile(r"takes back their last move", re.IGNORECASE)
_REMOVE_ROW   = re.compile(r"removes? (?:a )?row from ([A-K]\d{1,2}) to ([A-K]\d{1,2})", re.IGNORECASE)
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


def parse_bga_log(text: str) -> ParsedGame:
    """
    Parse a BGA Yinsh play log into a list of Move objects.
    Handles 'takes back their last move' by discarding the preceding pending move.
    """
    lines = text.strip().splitlines()
    player_map: dict[str, str] = {}
    metadata: dict[str, str] = {}
    moves: list[Move] = []

    # We need to pair up (place marker, move ring) into a single MoveRing.
    # BGA logs them as two consecutive lines.
    pending_marker: Optional[tuple[tuple[int,int], str]] = None  # (coord, player_name)
    # For undo: track the last confirmed move so we can pop it.
    # 'takes back their last move' undoes the *pending* marker+ring pair.

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _MOVE_HDR.match(line):
            continue

        # Extract player name: lines look like "<PlayerName> does something"
        # (unless it's a metadata line)
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        player_name, rest = parts[0], parts[1]

        if _TAKES_BACK.search(rest):
            # Undo: the pending marker hasn't been committed yet because we wait
            # for the matching ring-move line.  If there IS a pending marker, just
            # drop it.  If not, pop the last committed move.
            if pending_marker is not None:
                pending_marker = None
            elif moves:
                moves.pop()
            continue

        m = _PLACE_RING.search(rest)
        if m:
            coord = bga_to_xy(m.group(1))
            color = _name_to_color(player_name, player_map)
            moves.append(PlaceRing(coord=coord, color=color))
            continue

        m = _PLACE_MARKER.search(rest)
        if m:
            coord = bga_to_xy(m.group(1))
            # Don't emit yet; wait for the ring-move line
            pending_marker = (coord, player_name)
            continue

        m = _MOVE_RING.search(rest)
        if m:
            frm = bga_to_xy(m.group(1))
            to  = bga_to_xy(m.group(2))
            color = _name_to_color(player_name, player_map)
            if pending_marker is not None:
                # Sanity: frm should match where the marker was placed
                assert frm == pending_marker[0], (
                    f"Marker at {pending_marker[0]} but ring moved from {frm}"
                )
                pending_marker = None
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

    return ParsedGame(moves=moves, player_map=player_map, metadata=metadata)


# ---------------------------------------------------------------------------
# Game replay
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    """A rendered snapshot: the board state plus which cells to highlight."""
    board: BoardState
    highlight: set[tuple[int, int]]
    move_index: int   # 1-based move number shown in caption
    label: str        # short description e.g. "White places ring at E4"


def replay_game(parsed: ParsedGame) -> list[Frame]:
    """Replay all moves, capturing a Frame after every move."""
    board = BoardState()
    frames: list[Frame] = []

    # Initial empty board
    frames.append(Frame(
        board=board.copy(),
        highlight=set(),
        move_index=0,
        label="Start",
    ))

    for i, move in enumerate(parsed.moves, start=1):
        highlight: set[tuple[int, int]] = set()

        if isinstance(move, PlaceRing):
            board.place_ring(move.coord, move.color)
            highlight.add(move.coord)
            label = f"{move.color.capitalize()} places ring at {xy_to_bga(*move.coord)}"

        elif isinstance(move, MoveRing):
            board.move_ring(move.frm, move.to, move.color)
            highlight.add(move.frm)   # marker left behind
            highlight.add(move.to)    # ring's new position
            label = (f"{move.color.capitalize()} moves ring "
                     f"{xy_to_bga(*move.frm)} → {xy_to_bga(*move.to)}")

        elif isinstance(move, RemoveRow):
            board.remove_row(move.frm, move.to, move.color)
            # highlight the removed row cells
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

        else:
            label = "Unknown move"

        frames.append(Frame(
            board=board.copy(),
            highlight=highlight,
            move_index=i,
            label=label,
        ))

    return frames


# ---------------------------------------------------------------------------
# Hex board renderer — nodes-and-lines style (matches the C++ game)
# ---------------------------------------------------------------------------
#
# Node world positions (same formula as coords.cpp HVec2::to_world):
#   world_x = (x + y) * (sqrt3 / 2)
#   world_y = -(x - y) / 2          <- negated so y increases downward

SQRT3 = math.sqrt(3)


def _node_pos(x: int, y: int, spacing: float) -> tuple[float, float]:
    """Pixel position of node (x, y) with given inter-node spacing."""
    wx = (x + y) * (SQRT3 / 2)
    wy = -(x - y) / 2
    return wx * spacing, wy * spacing


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

    label_pad_left = int(spacing * 1.6)
    label_pad_top  = int(spacing * 1.4)
    pad            = int(spacing * 0.9)

    ox = -min_x + pad + label_pad_left   # pixel offset to apply to all coords
    oy = -min_y + pad + label_pad_top

    img_w = int(max_x - min_x + 2 * pad + label_pad_left)
    img_h = int(max_y - min_y + 2 * pad + label_pad_top)

    img  = Image.new("RGB", (img_w, img_h), BOARD_BG)
    draw = ImageDraw.Draw(img)

    line_w = max(1, spacing // 18)

    # --- draw lines along all 3 axis families ---

    # Family 1: x = const  (NE direction, y varies)
    for x in range(11):
        y0, y1 = BOARD_START_OFFSET[x], BOARD_END_OFFSET[x]
        if y0 >= y1:
            continue
        px0, py0 = _node_pos(x, y0, spacing)
        px1, py1 = _node_pos(x, y1, spacing)
        draw.line([(px0 + ox, py0 + oy), (px1 + ox, py1 + oy)],
                  fill=LINE_COLOR, width=line_w)

    # Family 2: y = const  (SE direction, x varies)
    for y in range(11):
        x0, x1 = BOARD_START_OFFSET[y], BOARD_END_OFFSET[y]
        if x0 >= x1:
            continue
        px0, py0 = _node_pos(x0, y, spacing)
        px1, py1 = _node_pos(x1, y, spacing)
        draw.line([(px0 + ox, py0 + oy), (px1 + ox, py1 + oy)],
                  fill=LINE_COLOR, width=line_w)

    # Family 3: x+y = const  (N direction, (-1,+1) steps)
    # x+y ranges from 5 to 15 for valid cells (columns A–K)
    for d in range(5, 16):
        # collect all valid nodes on this diagonal, sorted by y
        diag = sorted([(x, y) for (x, y) in VALID_CELLS if x + y == d], key=lambda p: p[1])
        if len(diag) < 2:
            continue
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

    for (x, y), (px, py) in nodes.items():
        cx, cy = px + ox, py + oy
        is_hi  = (x, y) in highlight

        if (x, y) in board.white_rings:
            _draw_ring(draw, cx, cy, ring_outer, ring_inner,
                       WHITE_COLOR, BLACK_COLOR, HIGHLIGHT_COLOR if is_hi else None)

        elif (x, y) in board.black_rings:
            _draw_ring(draw, cx, cy, ring_outer, ring_inner,
                       BLACK_COLOR, BLACK_COLOR, HIGHLIGHT_COLOR if is_hi else None)

        elif (x, y) in board.white_markers:
            fill = HIGHLIGHT_COLOR if is_hi else WHITE_COLOR
            draw.ellipse([cx - marker_r, cy - marker_r,
                          cx + marker_r, cy + marker_r],
                         fill=fill, outline=BLACK_COLOR, width=max(1, line_w))

        elif (x, y) in board.black_markers:
            fill = HIGHLIGHT_COLOR if is_hi else BLACK_COLOR
            draw.ellipse([cx - marker_r, cy - marker_r,
                          cx + marker_r, cy + marker_r],
                         fill=fill, outline=BLACK_COLOR, width=max(1, line_w))

    # --- coordinate labels ---
    font_sz    = max(7, spacing // 2)
    font_label = _load_font(font_sz)
    label_col  = "#444444"

    # Column letters A–K above the topmost node of each N-diagonal
    for d in range(5, 16):
        diag = [(x, y) for (x, y) in VALID_CELLS if x + y == d]
        if not diag:
            continue
        top = min(diag, key=lambda p: nodes[p][1])   # smallest pixel-y = topmost
        px, py = nodes[top]
        letter = chr(ord("A") + d - 5)
        draw.text((px + ox, py + oy - spacing * 0.85), letter,
                  fill=label_col, font=font_label, anchor="mm")

    # Row numbers 1–11 to the left of the leftmost node in each x-const column
    for x in range(11):
        col_nodes = [(x, y) for (_, y) in [(x, yy) for yy in range(11)] if (x, y) in VALID_CELLS
                     for y in [_]]  # just rebuild cleanly below
        col_nodes = [(x, y) for y in range(11) if (x, y) in VALID_CELLS]
        if not col_nodes:
            continue
        for (_, y) in col_nodes:
            px, py = nodes[(x, y)]
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
                caption_height: int = 22) -> Image.Image:
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

    sheet_w = cols * bw
    sheet_h = rows * (bh + caption_height)
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#F0E8D0")
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                                  max(9, caption_height - 4))
    except Exception:
        font = ImageFont.load_default()

    for idx, (img, frame) in enumerate(zip(board_imgs, frames)):
        col = idx % cols
        row = idx // cols
        x0 = col * bw
        y0 = row * (bh + caption_height)
        sheet.paste(img, (x0, y0))

        caption = f"#{frame.move_index}  {frame.label}"
        draw.text(
            (x0 + bw // 2, y0 + bh + caption_height // 2),
            caption, fill="#333333", font=font, anchor="mm",
        )

    return sheet


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Yinsh Game Sheet", layout="wide")
    st.title("Yinsh Game Sheet Renderer")
    st.markdown(
        "Paste a **Board Game Arena** Yinsh play log below, then click **Render**."
    )

    default_log = """\
Move 2 : 4/22/2026 11:20:04 PM
HardDiggler places a ring on D5
Move 4 : 4/23/2026 6:55:12 AM
7h48567b4 places a ring on K10
Move 6 : 11:34:37 AM
HardDiggler places a ring on H7
Move 8 : 3:35:23 PM
7h48567b4 places a ring on J11
Move 10 : 11:41:40 PM
HardDiggler places a ring on G8
Move 12 : 4/24/2026 7:14:12 AM
7h48567b4 places a ring on K7
Move 14 : 4/25/2026 12:04:11 AM
HardDiggler places a ring on H5
Move 16 : 6:56:21 AM
7h48567b4 places a ring on J5
Move 18 : 9:48:37 AM
HardDiggler places a ring on E4
Move 20 : 12:14:11 PM
7h48567b4 places a ring on J7
Move 22 : 1:05:18 PM
HardDiggler places a marker on E4
Move 23 : 1:05:22 PM
HardDiggler moves a ring from E4 to E5
Move 25 : 1:53:52 PM
7h48567b4 places a marker on K10
Move 26 : 1:53:53 PM
7h48567b4 moves a ring from K10 to J9
Move 28 : 11:37:17 PM
HardDiggler places a marker on E5
Move 29 : 11:37:21 PM
HardDiggler moves a ring from E5 to E6
Move 31 : 4/26/2026 6:53:26 AM
7h48567b4 places a marker on J5
Move 32 : 6:53:28 AM
7h48567b4 moves a ring from J5 to J6
Move 34 : 4/27/2026 12:21:53 AM
HardDiggler places a marker on E6
Move 35 : 12:21:54 AM
HardDiggler moves a ring from E6 to E7
Move 37 : 7:11:51 AM
7h48567b4 places a marker on J7
Move 38 : 7:12:00 AM
7h48567b4 moves a ring from J7 to J8
Move 39 : 7:12:03 AM
7h48567b4 takes back their last move
Move 40 : 7:12:08 AM
7h48567b4 places a marker on J9
Move 41 : 7:12:10 AM
7h48567b4 moves a ring from J9 to J8"""

    log_text = st.text_area("BGA play log", value=default_log, height=300)

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
        st.markdown("- Red highlight = last moved piece(s)")

    if st.button("Render", type="primary"):
        with st.spinner("Parsing and rendering…"):
            try:
                parsed = parse_bga_log(log_text)

                if not parsed.moves:
                    st.error("No moves were parsed. Check the log format.")
                    return

                frames = replay_game(parsed)

                if not show_start:
                    frames = frames[1:]  # drop the empty initial board

                if parsed.player_map:
                    names = ", ".join(f"{n} = {c}" for n, c in parsed.player_map.items())
                    st.info(f"Players: {names}  |  {len(parsed.moves)} moves parsed")

                sheet = build_sheet(frames, spacing=cell_size, cols=cols)

                # Display inline
                st.image(sheet, caption="Game sheet", use_container_width=True)

                # Download button
                buf = io.BytesIO()
                sheet.save(buf, format="PNG")
                buf.seek(0)
                st.download_button(
                    label="Download PNG",
                    data=buf,
                    file_name="yinsh_game_sheet.png",
                    mime="image/png",
                )

            except AssertionError as e:
                st.error(f"Game replay error: {e}")
            except Exception as e:
                st.exception(e)


if __name__ == "__main__":
    main()

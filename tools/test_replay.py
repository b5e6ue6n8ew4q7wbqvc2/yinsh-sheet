import sys, types

for mod in ['streamlit', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont']:
    sys.modules[mod] = types.ModuleType(mod)
import PIL.ImageFont as _pif
_pif.truetype = lambda *a, **k: (_ for _ in ()).throw(Exception())
_pif.load_default = lambda: None

sys.path.insert(0, '/home/bob/Sync/Programming/Yinsh/tools')
from app import parse_bga_log, replay_game

LOG = """Move 2 : 4/9/2026 2:38:08 PM
KivasFajo places a ring on F6
Move 4 : 3:51:24 PM
7h48567b4 places a ring on F7
Move 6 : 4:03:31 PM
KivasFajo places a ring on F5
Move 8 : 4:08:45 PM
7h48567b4 places a ring on E5
Move 10 : 4:11:24 PM
KivasFajo places a ring on G6
Move 12 : 4:14:22 PM
7h48567b4 places a ring on G5
Move 14 : 4:24:49 PM
KivasFajo places a ring on G7
Move 16 : 4:36:13 PM
7h48567b4 places a ring on H7
Move 18 : 6:15:39 PM
KivasFajo places a ring on E6
Move 20 : 6:42:43 PM
7h48567b4 places a ring on H6
Move 22 : 6:45:04 PM
KivasFajo places a marker on E6
Move 23 : 6:45:05 PM
KivasFajo moves a ring from E6 to D6
Move 24 : 6:45:17 PM
KivasFajo restarts their turn
Move 25 : 6:45:18 PM
KivasFajo places a marker on F5
Move 26 : 6:45:21 PM
KivasFajo moves a ring from F5 to E4
Move 28 : 6:55:26 PM
7h48567b4 places a marker on H6
Move 29 : 6:55:27 PM
7h48567b4 moves a ring from H6 to I6
Move 31 : 6:56:36 PM
KivasFajo places a marker on E4
Move 32 : 6:56:37 PM
KivasFajo moves a ring from E4 to D3
Move 34 : 6:57:26 PM
7h48567b4 places a marker on I6
Move 35 : 6:57:28 PM
7h48567b4 moves a ring from I6 to J6
Move 37 : 6:57:44 PM
KivasFajo places a marker on D3
Move 38 : 6:57:45 PM
KivasFajo moves a ring from D3 to B1
Move 40 : 6:58:17 PM
7h48567b4 places a marker on J6
Move 41 : 6:58:18 PM
7h48567b4 moves a ring from J6 to J5
Move 43 : 6:59:36 PM
KivasFajo places a marker on B1
Move 44 : 6:59:37 PM
KivasFajo moves a ring from B1 to C2
Move 46 : 6:59:44 PM
7h48567b4 places a marker on E5
Move 47 : 6:59:45 PM
7h48567b4 moves a ring from E5 to E3 and flips 1 markers
Move 49 : 7:05:23 PM
KivasFajo places a marker on E6
Move 50 : 7:05:24 PM
KivasFajo moves a ring from E6 to C4
Move 52 : 7:46:45 PM
7h48567b4 places a marker on E3
Move 53 : 7:46:48 PM
7h48567b4 moves a ring from E3 to F4
Move 55 : 9:16:08 PM
KivasFajo places a marker on C2
Move 56 : 9:16:09 PM
KivasFajo moves a ring from C2 to E2
Move 57 : 9:16:37 PM
KivasFajo restarts their turn
Move 58 : 9:16:38 PM
KivasFajo places a marker on F6
Move 59 : 9:16:40 PM
KivasFajo moves a ring from F6 to D4 and flips 1 markers
Move 60 : 9:17:13 PM
KivasFajo restarts their turn
Move 61 : 9:17:18 PM
KivasFajo places a marker on C2
Move 62 : 9:17:22 PM
KivasFajo takes back their last move
Move 63 : 9:17:24 PM
KivasFajo places a marker on C4
Move 64 : 9:17:26 PM
KivasFajo moves a ring from C4 to D5
Move 65 : 9:17:51 PM
KivasFajo restarts their turn
Move 66 : 9:18:13 PM
KivasFajo places a marker on C2
Move 67 : 9:18:30 PM
KivasFajo moves a ring from C2 to E2
Move 69 : 4/10/2026 7:20:43 AM
7h48567b4 places a marker on F7
Move 70 : 7:20:48 AM
7h48567b4 takes back their last move
Move 71 : 7:20:55 AM
7h48567b4 places a marker on G5
Move 72 : 7:20:59 AM
7h48567b4 moves a ring from G5 to D5 and flips 2 markers
Move 74 : 4/12/2026 5:55:13 PM
KivasFajo places a marker on G6
Move 75 : 5:55:28 PM
KivasFajo moves a ring from G6 to G4 and flips 1 markers
Move 77 : 5:58:59 PM
7h48567b4 places a marker on D5
Move 78 : 5:59:03 PM
7h48567b4 moves a ring from D5 to D4
Move 79 : 5:59:06 PM
7h48567b4 takes back their last move
Move 80 : 5:59:07 PM
7h48567b4 takes back their last move
Move 81 : 5:59:49 PM
7h48567b4 places a marker on D5
Move 82 : 5:59:51 PM
7h48567b4 moves a ring from D5 to D4
Move 84 : 6:00:18 PM
KivasFajo places a marker on G4
Move 85 : 6:00:19 PM
KivasFajo moves a ring from G4 to G3
Move 87 : 6:00:51 PM
7h48567b4 places a marker on H7
Move 88 : 6:00:55 PM
7h48567b4 moves a ring from H7 to H5 and flips 1 markers
Move 90 : 6:02:09 PM
KivasFajo places a marker on E2
Move 91 : 6:02:10 PM
KivasFajo moves a ring from E2 to E7 and flips 4 markers
Move 92 : 6:02:21 PM
KivasFajo restarts their turn
Move 93 : 6:02:27 PM
KivasFajo places a marker on G7
Move 94 : 6:02:28 PM
KivasFajo moves a ring from G7 to I7 and flips 1 markers
Move 96 : 6:04:54 PM
7h48567b4 places a marker on F4
Move 97 : 6:04:55 PM
7h48567b4 moves a ring from F4 to H4 and flips 1 markers
Move 99 : 6:06:52 PM
KivasFajo places a marker on E2
Move 100 : 6:06:54 PM
KivasFajo moves a ring from E2 to E7 and flips 4 markers
Move 102 : 6:07:27 PM
7h48567b4 places a marker on D4
Move 103 : 6:07:30 PM
7h48567b4 moves a ring from D4 to D2 and flips 1 markers
Move 105 : 6:12:17 PM
KivasFajo places a marker on F6
Move 106 : 6:12:18 PM
KivasFajo moves a ring from F6 to C3 and flips 2 markers
Move 107 : 6:12:44 PM
KivasFajo restarts their turn
Move 108 : 6:12:46 PM
KivasFajo places a marker on F6
Move 109 : 6:12:47 PM
KivasFajo moves a ring from F6 to D6 and flips 1 markers
Move 111 : 6:15:14 PM
7h48567b4 places a marker on D2
Move 112 : 6:15:19 PM
7h48567b4 moves a ring from D2 to D1
Move 114 : 6:16:03 PM
KivasFajo places a marker on G3
Move 115 : 6:16:05 PM
KivasFajo moves a ring from G3 to C3 and flips 2 markers
Move 116 : 6:17:22 PM
KivasFajo restarts their turn
Move 117 : 6:18:41 PM
KivasFajo places a marker on G3
Move 118 : 6:18:42 PM
KivasFajo moves a ring from G3 to C3 and flips 2 markers
Move 120 : 6:20:59 PM
7h48567b4 places a marker on D1
Move 121 : 6:21:01 PM
7h48567b4 moves a ring from D1 to F3 and flips 1 markers
Move 123 : 6:28:13 PM
KivasFajo places a marker on I7
Move 124 : 6:28:14 PM
KivasFajo moves a ring from I7 to I5 and flips 1 markers
Move 125 : 6:28:36 PM
KivasFajo restarts their turn
Move 126 : 6:28:39 PM
KivasFajo places a marker on D6
Move 127 : 6:28:41 PM
KivasFajo moves a ring from D6 to C5
Move 128 : 6:28:43 PM
KivasFajo removes a row of markers from D6 to H6
Move 129 : 6:29:29 PM
KivasFajo removes a ring from E7
Move 131 : 6:35:10 PM
7h48567b4 places a marker on H5
Move 132 : 6:35:16 PM
7h48567b4 moves a ring from H5 to I5
Move 134 : 6:35:32 PM
KivasFajo places a marker on C3
Move 135 : 6:35:33 PM
KivasFajo moves a ring from C3 to F6 and flips 2 markers
Move 137 : 6:36:24 PM
7h48567b4 places a marker on F3
Move 138 : 6:36:25 PM
7h48567b4 moves a ring from F3 to B3 and flips 3 markers
Move 139 : 6:36:31 PM
7h48567b4 removes a row of markers from E2 to I6
Move 140 : 6:36:39 PM
7h48567b4 removes a ring from J5
Move 142 : 6:38:00 PM
KivasFajo places a marker on C5
Move 143 : 6:38:01 PM
KivasFajo moves a ring from C5 to E7
Move 145 : 6:40:44 PM
7h48567b4 places a marker on B3
Move 146 : 6:40:45 PM
7h48567b4 moves a ring from B3 to B2
Move 148 : 6:47:20 PM
KivasFajo places a marker on I7
Move 149 : 6:47:21 PM
KivasFajo moves a ring from I7 to H6
Move 151 : 6:53:16 PM
7h48567b4 places a marker on I5
Move 152 : 6:53:19 PM
7h48567b4 moves a ring from I5 to H5
Move 154 : 4/13/2026 4:28:19 AM
KivasFajo places a marker on E7
Move 155 : 4:28:20 AM
KivasFajo moves a ring from E7 to E6
Move 156 : 4:28:54 AM
KivasFajo restarts their turn
Move 157 : 4:29:16 AM
KivasFajo places a marker on H6
Move 158 : 4:29:18 AM
KivasFajo moves a ring from H6 to H8 and flips 1 markers
Move 160 : 6:57:10 AM
7h48567b4 places a marker on H4
Move 161 : 6:57:12 AM
7h48567b4 moves a ring from H4 to F2 and flips 1 markers
Move 162 : 6:57:15 AM
7h48567b4 takes back their last move
Move 163 : 6:57:17 AM
7h48567b4 takes back their last move
Move 164 : 6:57:56 AM
7h48567b4 places a marker on H4
Move 165 : 6:57:57 AM
7h48567b4 moves a ring from H4 to F2 and flips 1 markers
Move 167 : 11:03:55 AM
KivasFajo places a marker on F6
Move 168 : 11:03:57 AM
KivasFajo moves a ring from F6 to F3 and flips 2 markers
Move 169 : 11:04:01 AM
KivasFajo removes a row of markers from E3 to I7
Move 170 : 11:04:46 AM
KivasFajo restarts their turn
Move 171 : 11:05:29 AM
KivasFajo places a marker on F6
Move 172 : 11:05:31 AM
KivasFajo moves a ring from F6 to F3 and flips 2 markers
Move 173 : 11:05:34 AM
KivasFajo removes a row of markers from E3 to I7
Move 174 : 11:10:59 AM
KivasFajo restarts their turn
Move 175 : 2:45:31 PM
KivasFajo places a marker on F6
Move 176 : 2:45:32 PM
KivasFajo moves a ring from F6 to F3 and flips 2 markers
Move 177 : 2:45:35 PM
KivasFajo removes a row of markers from E3 to I7
Move 178 : 2:49:37 PM
KivasFajo removes a ring from E7
Move 180 : 6:50:12 PM
7h48567b4 places a marker on F7
Move 181 : 6:50:14 PM
7h48567b4 moves a ring from F7 to F4 and flips 2 markers
Move 182 : 6:50:18 PM
7h48567b4 takes back their last move
Move 183 : 6:50:20 PM
7h48567b4 takes back their last move
Move 184 : 6:50:30 PM
7h48567b4 places a marker on F7
Move 185 : 6:50:39 PM
7h48567b4 moves a ring from F7 to F4 and flips 2 markers
Move 186 : 6:50:43 PM
7h48567b4 takes back their last move
Move 187 : 6:50:44 PM
7h48567b4 takes back their last move
Move 188 : 6:50:58 PM
7h48567b4 places a marker on F7
Move 189 : 6:50:59 PM
7h48567b4 moves a ring from F7 to F4 and flips 2 markers
Move 191 : 10:06:43 PM
KivasFajo places a marker on F3
Move 192 : 10:06:44 PM
KivasFajo moves a ring from F3 to E3
Move 193 : 10:10:13 PM
KivasFajo restarts their turn
Move 194 : 10:10:39 PM
KivasFajo places a marker on C4
Move 195 : 10:10:40 PM
KivasFajo moves a ring from C4 to B4
Move 196 : 10:11:27 PM
KivasFajo restarts their turn
Move 197 : 10:11:29 PM
KivasFajo places a marker on F3
Move 198 : 10:11:30 PM
KivasFajo moves a ring from F3 to H3 and flips 1 markers
Move 199 : 10:11:40 PM
KivasFajo restarts their turn
Move 200 : 10:11:42 PM
KivasFajo places a marker on F3
Move 201 : 10:11:44 PM
KivasFajo moves a ring from F3 to E3
Move 203 : 4/14/2026 6:52:40 AM
7h48567b4 places a marker on H5
Move 204 : 6:52:45 AM
7h48567b4 moves a ring from H5 to E2 and flips 1 markers
Move 206 : 7:07:25 AM
KivasFajo places a marker on H8
Move 207 : 7:07:29 AM
KivasFajo moves a ring from H8 to H6 and flips 1 markers
Move 209 : 7:14:03 AM
7h48567b4 places a marker on F2
Move 210 : 7:14:06 AM
7h48567b4 takes back their last move
Move 211 : 7:14:42 AM
7h48567b4 places a marker on B2
Move 212 : 7:14:44 AM
7h48567b4 moves a ring from B2 to I9 and flips 6 markers
Move 213 : 7:14:46 AM
7h48567b4 removes a row of markers from D1 to D5
Move 214 : 7:15:13 AM
7h48567b4 removes a ring from E2
Move 216 : 1:31:59 PM
KivasFajo places a marker on H6
Move 217 : 1:32:01 PM
KivasFajo moves a ring from H6 to H3 and flips 2 markers
Move 218 : 1:32:14 PM
KivasFajo restarts their turn
Move 219 : 1:32:16 PM
KivasFajo places a marker on E3
Move 220 : 1:32:18 PM
KivasFajo moves a ring from E3 to H3 and flips 2 markers
Move 221 : 1:32:31 PM
KivasFajo restarts their turn
Move 222 : 1:32:55 PM
KivasFajo places a marker on H6
Move 223 : 1:32:57 PM
KivasFajo moves a ring from H6 to H3 and flips 2 markers
Move 225 : 3:01:47 PM
7h48567b4 places a marker on F4
Move 226 : 3:01:55 PM
7h48567b4 moves a ring from F4 to I4 and flips 1 markers
Move 228 : 3:04:25 PM
KivasFajo places a marker on H3
Move 229 : 3:04:27 PM
KivasFajo moves a ring from H3 to H9 and flips 5 markers
Move 231 : 3:04:56 PM
7h48567b4 places a marker on I9
Move 232 : 3:04:57 PM
7h48567b4 moves a ring from I9 to D4 and flips 4 markers
Move 233 : 3:04:58 PM
7h48567b4 removes a row of markers from F3 to F7
Move 234 : 3:05:00 PM
7h48567b4 removes a ring from D4
7h48567b4 has removed 3 rings
End of game"""

try:
    parsed = parse_bga_log(LOG)
    print(f"Parsed {len(parsed.moves)} moves, players: {parsed.player_map}")
    frames, result = replay_game(parsed)
    print(f"SUCCESS: {len(frames)} frames, result: {result}")
except AssertionError as e:
    print(f"ASSERTION ERROR: {e}")
except Exception as e:
    import traceback; traceback.print_exc()

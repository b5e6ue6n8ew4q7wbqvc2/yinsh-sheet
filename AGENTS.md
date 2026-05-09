# Agent Context

## GitHub
- **My account**: b5e6ue6n8ew4q7wbqvc2
- **My repo**: https://github.com/b5e6ue6n8ew4q7wbqvc2/yinsh-sheet
- **Upstream (read-only)**: https://github.com/temhelk/yinsh
- **Remote `origin` must point to my repo**, not upstream.

## Project focus
- The repo contains two things:
  - `app.py` — Streamlit image sheet renderer, deployed on Streamlit Community Cloud
  - `yinsh-gui/` — C++ raylib game (our fork of upstream), built natively and as WebAssembly for itch.io
- `extern/` contains third-party libraries (raylib, raylib-cpp, raygui, yngine) — do not edit these.

## Workflow
- When changes are made, commit and push to `b5e6ue6n8ew4q7wbqvc2/yinsh-sheet` without being asked.
- Always verify `git remote get-url origin` is `https://github.com/b5e6ue6n8ew4q7wbqvc2/yinsh-sheet` before pushing. If it points to `temhelk/yinsh`, fix it first.
- `app.py` is hosted on Streamlit Community Cloud from the `master` branch, root `app.py`.
- Always test `app.py` changes by running through the parser/replay logic before pushing (use the Python binary at `/nix/store/14qr32kynfy2yidnxx4b5pqslb8jyjrb-python3-3.11.8-env/bin/python3` and stub out streamlit/PIL).
- `build/` and `build-web/` are gitignored — never commit them.

## Building the C++ game

### Native (for local testing)
```bash
nix-shell -p cmake ninja gcc xorg.libX11 xorg.libXrandr xorg.libXinerama \
          xorg.libXcursor xorg.libXi xorg.libXext libGL --run "
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -GNinja && cmake --build build
"
# Binary: build/yinsh-gui/Yinsh-gui
```

### Web (for itch.io)
```bash
# Configure (once, or after CMakeLists changes)
nix-shell -p emscripten cmake ninja python3 --run "
  EM_CACHE=/home/bob/.emscripten_cache \
  emcmake cmake -S . -B build-web -DCMAKE_BUILD_TYPE=Release -DPLATFORM=Web -GNinja
"

# Build
nix-shell -p emscripten cmake ninja python3 --run "
  EM_CACHE=/home/bob/.emscripten_cache cmake --build build-web
"

# Package for itch.io
cd build-web/yinsh-gui
cp Yinsh-gui.html index.html
zip ../../yinsh-web.zip index.html Yinsh-gui.js Yinsh-gui.wasm
```

Upload `yinsh-web.zip` to itch.io as HTML5 with **SharedArrayBuffer support** enabled.

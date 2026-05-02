# Agent Context

## GitHub
- **My account**: b5e6ue6n8ew4q7wbqvc2
- **My repo**: https://github.com/b5e6ue6n8ew4q7wbqvc2/yinsh-sheet
- **Upstream (read-only)**: https://github.com/temhelk/yinsh
- **Remote `origin` must point to my repo**, not upstream.

## Project focus
- We are only working on the Streamlit app: `app.py` (repo root)
- The C++ game (`yinsh-gui/`, `extern/`) is not our concern.

## Workflow
- When changes are made, commit and push to `b5e6ue6n8ew4q7wbqvc2/yinsh-sheet` without being asked.
- Always verify `git remote get-url origin` is `https://github.com/b5e6ue6n8ew4q7wbqvc2/yinsh-sheet` before pushing. If it points to `temhelk/yinsh`, fix it first.
- The app is hosted on Streamlit Community Cloud from the `master` branch, root `app.py`. Do NOT edit `tools/app.py` — it is a stale duplicate and is NOT what gets deployed.
- Always test changes by running `app.py` through the parser/replay logic before pushing (use the Python binary at `/nix/store/14qr32kynfy2yidnxx4b5pqslb8jyjrb-python3-3.11.8-env/bin/python3` and stub out streamlit/PIL).

# PrusaSlicer plugin server and MCP

`PrusaSlicer --plugin-server` starts a small HTTP server on 127.0.0.1 that runs
Lua through the plugin system, on the main thread, with the same sandbox as an
installed plugin. It writes `plugin-server.json` (host, port, token) into the
data directory and removes it on exit.

    GET  /ping                     -> {"ok": true, "version": "3.0.0-alpha11"}
    POST /lua  {"code": "<lua>"}   -> {"ok": bool, "output": "...", "result": "...", "error": "..."}

Every request needs `Authorization: Bearer <token>`. Each request becomes one
undo step, like a plugin run. Scripts run through the server may call
`api.project:export_gcode(path)`, which installed plugins may not.

## Client

`prusaslicer_client.py` needs only the Python standard library:

    ./prusaslicer_client.py --datadir ../build/datadir-dev ping
    ./prusaslicer_client.py --datadir ../build/datadir-dev run 'print(#api.project:objects())'

Or with curl:

    TOKEN=$(python3 -c 'import json;print(json.load(open("../build/datadir-dev/plugin-server.json"))["token"])')
    PORT=$(python3 -c 'import json;print(json.load(open("../build/datadir-dev/plugin-server.json"))["port"])')
    curl -H "Authorization: Bearer $TOKEN" -d '{"code":"print(#api.project:objects())"}' http://127.0.0.1:$PORT/lua

## MCP server

`prusaslicer_mcp.py` exposes the API as MCP tools:

- objects: `list_objects`, `place_object` (by footprint center), `move_object`,
  `rotate_object`, `scale_object`, `rename_object`, `select_object`,
  `remove_object`, `add_cube`, `bed_bounds`, `arrange`. Moves, rotations and
  scaling warn when the result lies outside the bed or above the print height.
- slicing: `slice` (waits by default), `slicing_status`, `export_gcode`
  (file or directory, waits for the file)
- settings: `get_setting`, `set_setting`, `list_settings` with scope
  `print`, `printer`, `material`/`filament` or `tool`
- presets: `current_presets`, `list_presets`, `select_preset` for print
  quality, filament, nozzle, printer and sheet
- import: `import_models` (STL, 3MF, OBJ, ... like File > Import)
- dialogs: `list_dialogs`, `close_dialog`, `close_all_dialogs`,
  `discard_crashed_projects` (dismisses the project recovery pane)
- printers: `account`, `list_printers`, `send_to_printer` (PrusaLink/OctoPrint
  printers saved as physical printers, or the logged-in Prusa Connect
  account's printers; actions upload, queue, print). The Connect path
  builds the same message as the upload web view; it has not yet been
  exercised against a live account, so verify with `upload` first.
- `run_lua` for anything else, `ping`

It needs the `mcp` package (Fedora: `python3-mcp`). Register it in Claude Code with:

    claude mcp add prusaslicer -e PRUSASLICER_DATADIR=/path/to/datadir -- python3 /path/to/prusaslicer_mcp.py

Leave `PRUSASLICER_DATADIR` unset to use the default PrusaSlicer data directory.

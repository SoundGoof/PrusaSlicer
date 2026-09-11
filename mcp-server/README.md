# PrusaSlicer plugin server and MCP

`PrusaSlicer --plugin-server` starts a small HTTP server on 127.0.0.1 that runs
Lua through the plugin system, on the main thread, with the same sandbox as an
installed plugin. It writes `plugin-server.json` (host, port, token) into the
data directory and removes it on exit.

    GET  /ping                     -> {"ok": true, "version": "3.0.0-alpha11"}
    POST /lua  {"code": "<lua>"}   -> {"ok": bool, "output": "...", "result": "...", "error": "..."}

Every request needs `Authorization: Bearer <token>`. Each request becomes one
undo step, like a plugin run.

## Client

`prusaslicer_client.py` needs only the Python standard library:

    ./prusaslicer_client.py --datadir ../build/datadir-dev ping
    ./prusaslicer_client.py --datadir ../build/datadir-dev run 'print(#api.project:objects())'

Or with curl:

    TOKEN=$(python3 -c 'import json;print(json.load(open("../build/datadir-dev/plugin-server.json"))["token"])')
    PORT=$(python3 -c 'import json;print(json.load(open("../build/datadir-dev/plugin-server.json"))["port"])')
    curl -H "Authorization: Bearer $TOKEN" -d '{"code":"print(#api.project:objects())"}' http://127.0.0.1:$PORT/lua

## MCP server

`prusaslicer_mcp.py` exposes the API as MCP tools (`list_objects`, `move_object`,
`rotate_object`, `scale_object`, `rename_object`, `remove_object`, `add_cube`,
`run_lua`, `ping`). It needs the `mcp` package. Register it in Claude Code with:

    claude mcp add prusaslicer -e PRUSASLICER_DATADIR=/path/to/datadir -- python3 /path/to/prusaslicer_mcp.py

Leave `PRUSASLICER_DATADIR` unset to use the default PrusaSlicer data directory.

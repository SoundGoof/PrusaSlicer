#!/usr/bin/env python3
"""MCP server that drives a running PrusaSlicer through its plugin server.

Requires the `mcp` package (Fedora: python3-mcp) and PrusaSlicer started with
--plugin-server. Every tool is a thin wrapper that sends Lua to PrusaSlicer;
the Lua plugin API (api.project, ModelElement, ConfigBox, ...) does the work.

Register in Claude Code with:

    claude mcp add prusaslicer -- python3 /path/to/prusaslicer_mcp.py
"""
import json
import os
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
from prusaslicer_client import PluginServerClient  # noqa: E402

mcp = FastMCP("prusaslicer")
_client = PluginServerClient(os.environ.get("PRUSASLICER_DATADIR"))

SCOPES = {
    "print": "bed:print_presets()",
    "printer": "bed:printer_presets()",
    "material": "bed:material_presets({index})",
    "filament": "bed:material_presets({index})",
    "tool": "bed:tool_print_presets({index})",
}


def _run(code: str) -> str:
    """Run Lua and return a readable summary, raising on Lua errors."""
    res = _client.run(code)
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or "unknown Lua error")
    parts = []
    if res.get("output"):
        parts.append(res["output"].rstrip("\n"))
    if res.get("result"):
        parts.append(f"=> {res['result']}")
    return "\n".join(parts) if parts else "ok"


def _run_json(code: str) -> dict:
    """Run Lua that returns a JSON string built by the _json helper."""
    res = _client.run(_JSON_HELPER + code)
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or "unknown Lua error")
    return json.loads(res.get("result") or "{}")


_JSON_HELPER = r"""
local function _json(v)
    local t = type(v)
    if t == "table" then
        if #v > 0 or next(v) == nil then
            local parts = {}
            for _, x in ipairs(v) do parts[#parts + 1] = _json(x) end
            return "[" .. table.concat(parts, ",") .. "]"
        end
        local parts = {}
        for k, x in pairs(v) do parts[#parts + 1] = string.format("%q:%s", tostring(k), _json(x)) end
        return "{" .. table.concat(parts, ",") .. "}"
    elseif t == "string" then
        return string.format("%q", v):gsub("\\\n", "\\n")
    elseif t == "number" or t == "boolean" then
        return tostring(v)
    else
        return "null"
    end
end
"""


def _lua_string(s: str) -> str:
    return json.dumps(s)  # JSON string literals are valid Lua string literals


def _lua_value(value: str) -> str:
    """Turn a user supplied string into a Lua literal: booleans, numbers, else string."""
    v = value.strip()
    if v.lower() in ("true", "false"):
        return v.lower()
    try:
        float(v)
        return v
    except ValueError:
        return _lua_string(value)


def _scope_expr(scope: str, index: int) -> str:
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    return SCOPES[scope].format(index=int(index))


# ---------------------------------------------------------------- basics

@mcp.tool()
def ping() -> str:
    """Check that PrusaSlicer is running with the plugin server enabled and report its version."""
    info = _client.ping()
    return f"PrusaSlicer {info.get('version')} at http://{_client.info['host']}:{_client.info['port']}"


@mcp.tool()
def run_lua(code: str) -> str:
    """Run arbitrary Lua in PrusaSlicer's plugin sandbox and return what it printed and returned.

    The `api` global is available: api.project:objects(), api.project:add_object{mesh=..., name=...},
    api.project:slice(), api.project:slicing_status(), api.project:export_gcode(path),
    api.project:current_bed():print_presets():value(key) / :set(key, value) / :keys(),
    api.make_cube(w, d, h) and the other mesh constructors. Object elements support name,
    object_id, instance_id, printable, position(), rotation(), scale(), bounds(), translate(),
    set_position(), rotate() [rad], scale_by(), set_scale(), set_name(), set_printable(), remove_object().
    """
    return _run(code)


# ---------------------------------------------------------------- objects

@mcp.tool()
def list_objects() -> str:
    """List every model instance on the plate with ids, position, rotation, scale and bounding box."""
    return _run(
        """
local els = api.project:objects()
if #els == 0 then print("no objects in project") end
for i, el in ipairs(els) do
    local c, r, s, b = el:center(), el:rotation(), el:scale(), el:bounds()
    print(string.format("#%d %s object=%d instance=%d printable=%s", i, el.name, el.object_id, el.instance_id, tostring(el.printable)))
    print(string.format("   center=(%.1f, %.1f) size=(%.1f x %.1f x %.1f) rot_deg=(%.1f, %.1f, %.1f) scale=(%.3f, %.3f, %.3f)",
        c.x, c.y, b.max_x - b.min_x, b.max_y - b.min_y, b.max_z - b.min_z, math.deg(r.x), math.deg(r.y), math.deg(r.z), s.x, s.y, s.z))
    print(string.format("   bounds=(%.2f, %.2f, %.2f)-(%.2f, %.2f, %.2f)", b.min_x, b.min_y, b.min_z, b.max_x, b.max_y, b.max_z))
end
"""
    )


_BED_CHECK = """
do
    local bed, b = api.project:bed_bounds(), target:bounds()
    if b.min_x < bed.min_x - 0.01 or b.min_y < bed.min_y - 0.01 or b.max_x > bed.max_x + 0.01 or b.max_y > bed.max_y + 0.01 then
        print(string.format("WARNING: %s is outside the bed (bed x %.0f..%.0f, y %.0f..%.0f; object x %.1f..%.1f, y %.1f..%.1f)",
            target.name, bed.min_x, bed.max_x, bed.min_y, bed.max_y, b.min_x, b.max_x, b.min_y, b.max_y))
    elseif bed.height > 0 and b.max_z > bed.height + 0.01 then
        print(string.format("WARNING: %s is taller than the printer allows (%.1f > %.1f mm)", target.name, b.max_z, bed.height))
    end
end
"""


def _select(object_id: int, instance_id: int | None) -> str:
    cond = f"el.object_id == {int(object_id)}"
    if instance_id is not None:
        cond += f" and el.instance_id == {int(instance_id)}"
    return f"""
local target
for _, el in ipairs(api.project:objects()) do
    if {cond} then target = el break end
end
if not target then error("no such object/instance") end
"""


@mcp.tool()
def move_object(object_id: int, dx: float = 0, dy: float = 0, dz: float = 0, instance_id: int | None = None) -> str:
    """Move an object instance by dx, dy, dz millimetres. Use list_objects to find ids."""
    return _run(_select(object_id, instance_id) + f"target:translate({dx}, {dy}, {dz})\nlocal c = target:center()\nprint(string.format('%s now centered at (%.1f, %.1f)', target.name, c.x, c.y))" + _BED_CHECK)


@mcp.tool()
def place_object(object_id: int, x: float, y: float, instance_id: int | None = None) -> str:
    """Place an object so the center of its footprint is at bed coordinates x, y (millimetres).
    Use bed_bounds to see the printable area. This is what "put it at 100, 100" means to a user."""
    return _run(_select(object_id, instance_id) + f"target:set_center({x}, {y})\nlocal c = target:center()\nprint(string.format('%s centered at (%.1f, %.1f)', target.name, c.x, c.y))" + _BED_CHECK)


@mcp.tool()
def set_position(object_id: int, x: float, y: float, z: float = 0, instance_id: int | None = None) -> str:
    """Set the instance origin to x, y, z. The origin is usually not the visual center; prefer place_object."""
    return _run(_select(object_id, instance_id) + f"target:set_position({x}, {y}, {z})\nprint('ok')" + _BED_CHECK)


@mcp.tool()
def rotate_object(object_id: int, rx_deg: float = 0, ry_deg: float = 0, rz_deg: float = 0, instance_id: int | None = None) -> str:
    """Rotate an object instance around its origin by the given angles in degrees (world axes)."""
    return _run(_select(object_id, instance_id) + f"target:rotate(math.rad({rx_deg}), math.rad({ry_deg}), math.rad({rz_deg}))\nprint('ok')" + _BED_CHECK)


@mcp.tool()
def scale_object(object_id: int, factor: float, instance_id: int | None = None) -> str:
    """Scale an object instance uniformly by the given factor (2 doubles the size)."""
    return _run(_select(object_id, instance_id) + f"target:scale_by({factor}, {factor}, {factor})\nprint('ok')" + _BED_CHECK)


@mcp.tool()
def rename_object(object_id: int, name: str) -> str:
    """Rename a model object."""
    return _run(_select(object_id, None) + f"target:set_name({_lua_string(name)})\nprint('ok')")


@mcp.tool()
def select_object(object_id: int | None = None, instance_id: int | None = None) -> str:
    """Highlight an object in the 3D view, or clear the selection when no id is given."""
    if object_id is None:
        return _run("api.project:clear_selection()\nprint('selection cleared')")
    return _run(_select(object_id, instance_id) + "target:select()\nprint('selected ' .. target.name)")


@mcp.tool()
def remove_object(object_id: int) -> str:
    """Remove a model object and all of its instances from the plate."""
    return _run(_select(object_id, None) + "target:remove_object()\nprint('removed')")


@mcp.tool()
def bed_bounds() -> str:
    """Printable area of the selected bed in world millimetres, and the maximum print height."""
    return json.dumps(_run_json("return _json(api.project:bed_bounds())"))


@mcp.tool()
def arrange(wait_s: float = 3.0) -> str:
    """Auto-arrange all printable objects on the bed, like the Arrange button. Runs in the background;
    waits wait_s seconds and then reports the resulting positions."""
    _run("api.project:arrange()")
    time.sleep(wait_s)
    return list_objects()


@mcp.tool()
def import_models(paths: list[str]) -> str:
    """Import model files (STL, 3MF, OBJ, ...) onto the plate, like File > Import, and arrange them.

    Paths must be absolute. Returns the ids of the added objects, which the other tools use.
    """
    lua_paths = ", ".join(_lua_string(str(Path(p).expanduser().resolve())) for p in paths)
    return _run(
        f"local added = api.project:import_models({{{lua_paths}}})\n"
        "for _, el in ipairs(added) do local b = el:bounds()\n"
        "  print(string.format('added %s object=%d instance=%d size=(%.1f x %.1f x %.1f) mm', el.name, el.object_id, el.instance_id, b.max_x - b.min_x, b.max_y - b.min_y, b.max_z - b.min_z)) end\n"
        "if #added == 0 then print('nothing imported') end"
    )


@mcp.tool()
def add_cube(width: float, depth: float, height: float, name: str = "Cube") -> str:
    """Add a box of the given size in millimetres to the plate."""
    return _run(
        f"local el = api.project:add_object{{mesh = api.make_cube({width}, {depth}, {height}), name = {_lua_string(name)}}}\n"
        "print(string.format('added %s as object %d', el.name, el.object_id))"
    )


# ---------------------------------------------------------------- slicing and export

def _status() -> dict:
    return _run_json("return _json(api.project:slicing_status())")


@mcp.tool()
def slicing_status() -> str:
    """Report the slicing state of the selected bed: code, progress, errors."""
    return json.dumps(_status(), indent=2)


@mcp.tool()
def slice(wait: bool = True, timeout_s: float = 600) -> str:
    """Slice the selected bed. With wait=True (default) blocks until slicing finished or failed."""
    _run("api.project:slice()")
    if not wait:
        return "slicing started"
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        st = _status()
        last = st
        if st.get("finished"):
            return "slicing finished"
        if st.get("failed"):
            return f"slicing failed ({st.get('code')}): {st.get('errors', '').strip()}"
        time.sleep(0.5)
    return f"timed out after {timeout_s}s, last status: {json.dumps(last)}"


@mcp.tool()
def export_gcode(path: str, wait: bool = True, timeout_s: float = 300) -> str:
    """Export the finished slicing result as G-code to a file or into a directory.

    If path is a directory the configured output filename is used. Slice first.
    With wait=True (default) waits until the file exists and stops growing.
    """
    dest = _run("return api.project:export_gcode(" + _lua_string(path) + ")").removeprefix("=> ")
    if not wait:
        return f"export started: {dest}"
    p = Path(dest)
    deadline = time.monotonic() + timeout_s
    last_size = -1
    stable = 0
    while time.monotonic() < deadline:
        if p.exists():
            size = p.stat().st_size
            if size == last_size and size > 0:
                stable += 1
                if stable >= 3:
                    return f"exported {dest} ({size} bytes)"
            else:
                stable = 0
            last_size = size
        time.sleep(0.5)
    return f"timed out waiting for {dest}"


# ---------------------------------------------------------------- presets

PRESET_KINDS = ("printer", "print", "material", "nozzle", "sheet")


def _kind(kind: str) -> str:
    k = kind.strip().lower()
    aliases = {"filament": "material", "quality": "print", "tool": "nozzle", "bed": "sheet"}
    k = aliases.get(k, k)
    if k not in PRESET_KINDS:
        raise ValueError(f"kind must be one of {', '.join(PRESET_KINDS)} (aliases: filament, quality)")
    return k


@mcp.tool()
def list_presets(kind: str = "print", index: int = 0) -> str:
    """List selectable presets. kind: printer (printer model and nozzle variants), print (quality profiles
    such as 0.15mm QUALITY), material or filament (per slot index), nozzle (per tool index), sheet.
    The selected one is marked with *.
    """
    k = _kind(kind)
    rows = _run_json(f"return _json(api.presets:list({_lua_string(k)}, {int(index)}))")
    lines = []
    for r in rows:
        mark = "*" if r.get("selected") else " "
        extra = f"  [{r['printer']}]" if r.get("printer") else ""
        lines.append(f"{mark} {r['name']}{extra}")
    return "\n".join(lines) if lines else "no presets"


@mcp.tool()
def select_preset(kind: str, name: str, index: int = 0) -> str:
    """Switch a preset by name: kind print/quality (e.g. "0.15mm QUALITY"), material/filament
    (e.g. "Prusament PETG"), nozzle (e.g. "0.6"), printer, or sheet. A unique part of the name is enough.
    Unsaved edits to the previous preset are dropped, like choosing it in the sidebar.
    """
    k = _kind(kind)
    return _run(f"print('selected ' .. api.presets:select({_lua_string(k)}, {_lua_string(name)}, {int(index)}))")


@mcp.tool()
def current_presets() -> str:
    """Show the selected printer, print quality, filament(s), nozzle(s) and sheet."""
    return _run(
        """
print("printer:  " .. api.presets:selected("printer"))
print("print:    " .. api.presets:selected("print"))
local bed = api.project:current_bed()
local tools = bed:printer_config().tool_count
for i = 0, tools - 1 do
    print(string.format("tool %d:   nozzle %s, material %s", i, api.presets:selected("nozzle", i), api.presets:selected("material", i)))
end
print("sheet:    " .. api.presets:selected("sheet"))
"""
    )


# ---------------------------------------------------------------- dialogs

@mcp.tool()
def list_dialogs() -> str:
    """List the application's dialogs and which of them are open right now."""
    d = _run_json("return _json(api.ui:dialogs())")
    open_ones = sorted(k for k, v in d.items() if v)
    closed = sorted(k for k, v in d.items() if not v)
    return f"open: {', '.join(open_ones) or 'none'}\nclosed: {', '.join(closed)}"


@mcp.tool()
def close_dialog(name: str) -> str:
    """Close one dialog by name, e.g. crashed_projects, welcome, preferences, print_settings. See list_dialogs."""
    return _run(f"if api.ui:close_dialog({_lua_string(name)}) then print('closed') else error('unknown dialog: ' .. {_lua_string(name)}) end")


@mcp.tool()
def close_all_dialogs() -> str:
    """Close every open dialog so the plater is usable again."""
    return _run("api.ui:close_dialogs()\nprint('all dialogs closed')")


@mcp.tool()
def discard_crashed_projects() -> str:
    """Dismiss the project recovery pane and discard the recovered (autosaved) projects."""
    return _run("api.ui:discard_crashed_projects()\nprint('recovery pane dismissed, projects discarded')")


# ---------------------------------------------------------------- settings

@mcp.tool()
def get_setting(key: str, scope: str = "print", index: int = 0) -> str:
    """Read a slicer setting. scope: print, printer, material (filament) or tool; index selects the tool/material slot, starting at 0.

    Examples: layer_height, fill_density, perimeters (print); nozzle_diameter (tool); temperature (material).
    """
    box = _scope_expr(scope, index)
    value = _run_json(f"local bed = api.project:current_bed()\nreturn _json({{value = {box}:value({_lua_string(key)})}})").get("value")
    return json.dumps(value) if isinstance(value, (list, dict)) else str(value)


@mcp.tool()
def set_setting(key: str, value: str, scope: str = "print", index: int = 0) -> str:
    """Change a slicer setting for the current project. value is a string: numbers, true/false and
    percentages like "15%" are accepted. scope: print, printer, material (filament) or tool.
    """
    box = _scope_expr(scope, index)
    k = _lua_string(key)
    return _run(
        f"local bed = api.project:current_bed()\nlocal b = {box}\nb:set({k}, {_lua_value(value)})\n"
        f"print({k} .. ' = ' .. tostring(b:value({k})))"
    )


@mcp.tool()
def list_settings(scope: str = "print", index: int = 0, contains: str = "") -> str:
    """List available setting keys in a scope, optionally only those containing a substring."""
    box = _scope_expr(scope, index)
    out = _run(
        f"local bed = api.project:current_bed()\nlocal keys = {box}:keys()\ntable.sort(keys)\n"
        f"local filter = {_lua_string(contains)}\n"
        "for _, k in ipairs(keys) do if filter == '' or string.find(k, filter, 1, true) then print(k) end end"
    )
    return out


if __name__ == "__main__":
    mcp.run()

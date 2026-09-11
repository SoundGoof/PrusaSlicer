#!/usr/bin/env python3
"""MCP server that drives a running PrusaSlicer through its plugin server.

Requires the `mcp` package (pip install mcp) and PrusaSlicer started with
--plugin-server. Every tool is a thin wrapper that sends Lua to PrusaSlicer;
the Lua plugin API (api.project, ModelElement, ...) does the actual work.

Register in Claude Code with:

    claude mcp add prusaslicer -- python3 /path/to/prusaslicer_mcp.py
"""
import json
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
from prusaslicer_client import PluginServerClient  # noqa: E402

mcp = FastMCP("prusaslicer")
_client = PluginServerClient(os.environ.get("PRUSASLICER_DATADIR"))


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


def _lua_string(s: str) -> str:
    return json.dumps(s)  # JSON string literals are valid Lua string literals


@mcp.tool()
def ping() -> str:
    """Check that PrusaSlicer is running with the plugin server enabled and report its version."""
    info = _client.ping()
    return f"PrusaSlicer {info.get('version')} at http://{_client.info['host']}:{_client.info['port']}"


@mcp.tool()
def run_lua(code: str) -> str:
    """Run arbitrary Lua in PrusaSlicer's plugin sandbox and return what it printed and returned.

    The `api` global is available, e.g. `api.project:objects()`, `api.make_cube(w, h, d)`,
    `api.project:add_object{mesh = ...}`. Object elements support name, object_id, instance_id,
    printable, position(), rotation(), scale(), bounds(), translate(dx, dy, dz),
    set_position(x, y, z), rotate(rx, ry, rz) [rad], scale_by(sx, sy, sz), set_scale(sx, sy, sz),
    set_name(name), set_printable(bool) and remove_object().
    """
    return _run(code)


@mcp.tool()
def list_objects() -> str:
    """List every model instance on the plate with ids, position, rotation, scale and bounding box."""
    return _run(
        """
local els = api.project:objects()
if #els == 0 then print("no objects in project") end
for i, el in ipairs(els) do
    local p, r, s, b = el:position(), el:rotation(), el:scale(), el:bounds()
    print(string.format("#%d %s object=%d instance=%d printable=%s", i, el.name, el.object_id, el.instance_id, tostring(el.printable)))
    print(string.format("   pos=(%.2f, %.2f, %.2f) rot_deg=(%.1f, %.1f, %.1f) scale=(%.3f, %.3f, %.3f)",
        p.x, p.y, p.z, math.deg(r.x), math.deg(r.y), math.deg(r.z), s.x, s.y, s.z))
    print(string.format("   bounds=(%.2f, %.2f, %.2f)-(%.2f, %.2f, %.2f)", b.min_x, b.min_y, b.min_z, b.max_x, b.max_y, b.max_z))
end
"""
    )


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
    return _run(_select(object_id, instance_id) + f"target:translate({dx}, {dy}, {dz})\nlocal p = target:position()\nprint(string.format('%s now at (%.2f, %.2f, %.2f)', target.name, p.x, p.y, p.z))")


@mcp.tool()
def set_position(object_id: int, x: float, y: float, z: float = 0, instance_id: int | None = None) -> str:
    """Place an object instance so its origin is at world position x, y, z millimetres."""
    return _run(_select(object_id, instance_id) + f"target:set_position({x}, {y}, {z})\nprint('ok')")


@mcp.tool()
def rotate_object(object_id: int, rx_deg: float = 0, ry_deg: float = 0, rz_deg: float = 0, instance_id: int | None = None) -> str:
    """Rotate an object instance around its origin by the given angles in degrees (world axes)."""
    return _run(_select(object_id, instance_id) + f"target:rotate(math.rad({rx_deg}), math.rad({ry_deg}), math.rad({rz_deg}))\nprint('ok')")


@mcp.tool()
def scale_object(object_id: int, factor: float, instance_id: int | None = None) -> str:
    """Scale an object instance uniformly by the given factor (2 doubles the size)."""
    return _run(_select(object_id, instance_id) + f"target:scale_by({factor}, {factor}, {factor})\nprint('ok')")


@mcp.tool()
def rename_object(object_id: int, name: str) -> str:
    """Rename a model object."""
    return _run(_select(object_id, None) + f"target:set_name({_lua_string(name)})\nprint('ok')")


@mcp.tool()
def remove_object(object_id: int) -> str:
    """Remove a model object and all of its instances from the plate."""
    return _run(_select(object_id, None) + "target:remove_object()\nprint('removed')")


@mcp.tool()
def add_cube(width: float, depth: float, height: float, name: str = "Cube") -> str:
    """Add a box of the given size in millimetres to the plate."""
    return _run(
        f"local el = api.project:add_object{{mesh = api.make_cube({width}, {depth}, {height}), name = {_lua_string(name)}}}\n"
        "print(string.format('added %s as object %d', el.name, el.object_id))"
    )


if __name__ == "__main__":
    mcp.run()

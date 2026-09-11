info = {
    id = "com.soundgoof.scene.nudge",
    type = "project.plugin",
    title = "Nudge objects",
    menu = "Scene/Nudge objects",
    params = {
        {name = "dx", label = "Move X [mm]", type = "float", default = 10},
        {name = "dy", label = "Move Y [mm]", type = "float", default = 0},
        {name = "rz", label = "Rotate Z [deg]", type = "float", default = 0},
        {name = "scale", label = "Scale factor", type = "float", default = 1},
    }
}

function execute(opts)
    local elements = api.project:objects()
    for i, el in ipairs(elements) do
        local before = el:position()
        el:translate(opts.dx, opts.dy, 0)
        if opts.rz ~= 0 then
            el:rotate(0, 0, math.rad(opts.rz))
        end
        if opts.scale ~= 1 then
            el:scale_by(opts.scale, opts.scale, opts.scale)
        end
        local after = el:position()
        print(string.format("%s: (%.2f, %.2f, %.2f) -> (%.2f, %.2f, %.2f)",
            el.name, before.x, before.y, before.z, after.x, after.y, after.z))
    end
end

info = {
    id = "com.soundgoof.scene.list_objects",
    type = "project.plugin",
    title = "List objects",
    menu = "Scene/List objects",
    params = {}
}

function execute(opts)
    local elements = api.project:objects()
    print(string.format("%d instance(s) in project", #elements))
    for i, el in ipairs(elements) do
        local p = el:position()
        local r = el:rotation()
        local s = el:scale()
        local b = el:bounds()
        print(string.format(
            "#%d %s  object=%d instance=%d printable=%s",
            i, el.name, el.object_id, el.instance_id, tostring(el.printable)))
        print(string.format(
            "    pos=(%.2f, %.2f, %.2f)  rot=(%.3f, %.3f, %.3f)  scale=(%.2f, %.2f, %.2f)",
            p.x, p.y, p.z, r.x, r.y, r.z, s.x, s.y, s.z))
        print(string.format(
            "    bounds=(%.2f, %.2f, %.2f) - (%.2f, %.2f, %.2f)",
            b.min_x, b.min_y, b.min_z, b.max_x, b.max_y, b.max_z))
    end
end

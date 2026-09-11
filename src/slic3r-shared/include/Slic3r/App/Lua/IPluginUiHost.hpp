#pragma once

#include <string>
#include <vector>

namespace Slic3r::App::Lua {

/**
 * @brief UI operations the plugin API may perform, implemented by the plater.
 *
 * Kept deliberately small: scripts can see which dialogs are open and close
 * them, which is what an external controller needs to get the application
 * back into a usable state (crash recovery pane, welcome dialog, ...).
 */
class IPluginUiHost
{
public:
    struct DialogInfo
    {
        std::string name;
        bool open{false};
    };

    virtual ~IPluginUiHost() = default;

    /** All dialogs known by name and whether each is currently open. */
    virtual std::vector<DialogInfo> dialogs() const = 0;

    /** Close one dialog by name. Returns false when the name is unknown. */
    virtual bool close_dialog(const std::string& name) = 0;

    /** Close every dialog. */
    virtual void close_all_dialogs() = 0;

    /** Dismiss the crash recovery dialog and discard the recovered projects. */
    virtual void discard_crashed_projects() = 0;
};

} // namespace Slic3r::App::Lua

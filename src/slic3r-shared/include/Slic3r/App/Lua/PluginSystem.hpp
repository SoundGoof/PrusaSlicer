#pragma once
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "Slic3r/App/Lua/PluginRegistry.hpp"
#include "Slic3r/App/Lua/IPluginRescanListener.hpp"
#include "Slic3r/App/Lua/IPluginInstallationListener.hpp"
#include "Slic3r/Biz/ProjectInteractor.hpp"
#include "Slic3r/Biz/Emboss/IFontManager.hpp"
#include "Slic3r/Biz/Platform//WithListeners.hpp"
#include "Slic3r/App/Yoga/Item.hpp"

namespace Slic3r::App::Lua {

class PluginDialog;
class PluginServer;

class PluginSystem : public WithListeners<IPluginRescanListener, IPluginInstallationListener>
{
public:
    struct ExecutionResult
    {
        bool ok{false};
        std::string output; // everything the script printed
        std::string result; // the chunk's return value, converted with tostring
        std::string error;  // error message when ok is false
    };

    explicit PluginSystem(
        std::initializer_list<std::string> plugin_paths,
        Biz::ProjectInteractor& project_interactor,
        Biz::Emboss::IFontManager& font_manager
    );
    ~PluginSystem();

    void execute_plugin(const std::string& id);

    /** Run a Lua chunk with the plugin API and sandbox. Must be called on the main thread. */
    ExecutionResult execute_source(const std::string& source, const std::string& chunk_name);

    /** Start the local plugin server if it was requested on the command line. */
    void start_server_if_requested();
    void stop_server();
    void rescan();
    const auto& plugins() const { return m_registry.plugins(); }

    void install(const std::string& zip_file_path);

    Yoga::Passthrough<PluginDialog>& init_dialog();
private:
    void clear();
    void scan(const std::string& path);
    void finalize_run();
private:
    struct PluginData
    {
        PluginMeta meta;
        PluginParamValueMap param_values;
    };

    PluginRegistry m_registry;
    std::vector<std::string> m_plugin_paths;
    Biz::ProjectInteractor& m_project_interactor;
    Biz::Emboss::IFontManager& m_font_manager;
    std::optional<PluginData> m_current_plugin_data, m_last_plugin_data;
    Yoga::Passthrough<PluginDialog> m_dialog;
    std::unique_ptr<PluginServer> m_server;
};

} // namespace Slic3r::App::Lua

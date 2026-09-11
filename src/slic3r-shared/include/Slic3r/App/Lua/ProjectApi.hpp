#pragma once

#include "Slic3r/Directories.hpp"
#include "Slic3r/Biz/Lua/LuaEngine.hpp"
#include "Slic3r/Biz/ProjectInteractor.hpp"
#include "Slic3r/Biz/Emboss/IFontManager.hpp"
#include "Slic3r/Biz/Emboss/TextPresetManager.hpp"
#include "Slic3r/App/Lua/IPluginUiHost.hpp"

namespace Slic3r::App::Lua {

/** What a script is allowed to do beyond the plugin sandbox. */
struct ApiPermissions
{
    bool export_files{false}; // api.project:export_gcode(path) may write anywhere on disk
    bool import_files{false}; // api.project:import_models(paths) may read model files anywhere on disk
    bool send_to_printer{false}; // api.printers:send() may upload to printers and Prusa Connect
};

class ProjectApi
{
public:
    using Permissions = ApiPermissions;

    ProjectApi(
        Biz::ProjectInteractor& project_interactor,
        Biz::Emboss::IFontManager& font_manager,
        Permissions permissions = Permissions(),
        IPluginUiHost* ui_host  = nullptr
    );

    void register_api(Biz::Lua::LuaEngine& lua);

private:
    Biz::ProjectInteractor& m_project_interactor;
    Biz::Emboss::IFontManager& m_font_manager;
    Permissions m_permissions;
    IPluginUiHost* m_ui_host;
    Biz::Emboss::TextPresetManager m_text_preset_manager;
    Domain::FontList m_fav_fonts;
};

}
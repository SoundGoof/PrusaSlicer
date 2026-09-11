#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <thread>

namespace Slic3r::App::Lua {

class PluginSystem;

/**
 * @brief Local HTTP server that runs Lua code through the plugin system.
 *
 * Listens on 127.0.0.1 on a free port. The port and a random bearer token are
 * written to <data_dir>/plugin-server.json so a local client can find it.
 * Every request is executed on the main thread with the same sandbox as an
 * installed plugin. Off by default, enabled with --plugin-server.
 *
 * Endpoints:
 *   GET  /ping            -> {"ok":true,"version":...}
 *   POST /lua {"code":..} -> {"ok":bool,"output":..,"result":..,"error":..}
 */
class PluginServer
{
public:
    static void set_requested(bool requested);
    static bool requested();

    explicit PluginServer(PluginSystem& plugin_system);
    ~PluginServer();

    bool start();
    void stop();

    uint16_t port() const { return m_port; }
    const std::string& info_file() const { return m_info_file; }

private:
    struct Impl;

    void run();
    std::string handle_request(
        const std::string& method,
        const std::string& target,
        const std::string& authorization,
        const std::string& body,
        unsigned& status
    );

    PluginSystem& m_plugin_system;
    std::unique_ptr<Impl> m_impl;
    std::thread m_thread;
    std::atomic<bool> m_running{false};
    uint16_t m_port{0};
    std::string m_token;
    std::string m_info_file;
};

} // namespace Slic3r::App::Lua

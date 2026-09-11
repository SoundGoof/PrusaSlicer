#include "Slic3r/App/Lua/PluginServer.hpp"
#include "Slic3r/App/Lua/PluginSystem.hpp"
#include "Slic3r/Directories.hpp"
#include "Slic3r/Biz/Platform/PlatformServices.hpp"
#include "Slic3r/Biz/Platform/IMainThreadDispatcher.hpp"
#include "Slic3r/Version.hpp"

#include <boost/asio/io_context.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/http.hpp>
#include <boost/filesystem.hpp>
#include <boost/nowide/fstream.hpp>
#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>

#include <chrono>
#include <future>
#include <random>

namespace Slic3r::App::Lua {

namespace beast = boost::beast;
namespace http  = beast::http;
using tcp       = boost::asio::ip::tcp;

namespace {

std::atomic<bool> g_requested{false};

// Random hex string used as the bearer token for this process lifetime.
std::string make_token(size_t bytes = 24)
{
    std::random_device rd;
    std::uniform_int_distribution<int> dist(0, 255);
    static const char* hex = "0123456789abcdef";
    std::string out;
    out.reserve(bytes * 2);
    for (size_t i = 0; i < bytes; ++i) {
        const int v = dist(rd);
        out += hex[v >> 4];
        out += hex[v & 0xf];
    }
    return out;
}

constexpr auto REQUEST_TIMEOUT = std::chrono::seconds(120);

} // namespace

struct PluginServer::Impl
{
    boost::asio::io_context ioc;
    tcp::acceptor acceptor{ioc};
};

void PluginServer::set_requested(bool requested) { g_requested = requested; }
bool PluginServer::requested() { return g_requested; }

PluginServer::PluginServer(PluginSystem& plugin_system) :
    m_plugin_system(plugin_system),
    m_impl(std::make_unique<Impl>())
{}

PluginServer::~PluginServer() { stop(); }

bool PluginServer::start()
{
    if (m_running) {
        return true;
    }
    boost::system::error_code ec;
    const tcp::endpoint endpoint(boost::asio::ip::make_address("127.0.0.1"), 0);
    m_impl->acceptor.open(endpoint.protocol(), ec);
    if (!ec) m_impl->acceptor.set_option(boost::asio::socket_base::reuse_address(true), ec);
    if (!ec) m_impl->acceptor.bind(endpoint, ec);
    if (!ec) m_impl->acceptor.listen(boost::asio::socket_base::max_listen_connections, ec);
    if (ec) {
        SPDLOG_ERROR("Plugin server: cannot listen on 127.0.0.1: {}", ec.message());
        return false;
    }
    m_port  = m_impl->acceptor.local_endpoint().port();
    m_token = make_token();

    // Advertise port and token in the data dir, readable only by the current user.
    const boost::filesystem::path info_path = boost::filesystem::path(data_dir()) / "plugin-server.json";
    m_info_file = info_path.string();
    {
        nlohmann::json info;
        info["host"]  = "127.0.0.1";
        info["port"]  = m_port;
        info["token"] = m_token;
        boost::nowide::ofstream f(m_info_file);
        f << info.dump(2) << std::endl;
    }
    boost::filesystem::permissions(info_path, boost::filesystem::owner_read | boost::filesystem::owner_write, ec);

    m_running = true;
    m_thread  = std::thread([this] { run(); });
    SPDLOG_INFO("Plugin server listening on http://127.0.0.1:{} (token in {})", m_port, m_info_file);
    return true;
}

void PluginServer::stop()
{
    if (!m_running) {
        return;
    }
    m_running = false;
    boost::system::error_code ec;
    m_impl->acceptor.close(ec); // unblocks the pending accept()
    if (m_thread.joinable()) {
        m_thread.join();
    }
    boost::filesystem::remove(m_info_file, ec);
    SPDLOG_INFO("Plugin server stopped");
}

void PluginServer::run()
{
    while (m_running) {
        tcp::socket socket(m_impl->ioc);
        boost::system::error_code ec;
        m_impl->acceptor.accept(socket, ec);
        if (ec) {
            if (m_running) {
                SPDLOG_WARN("Plugin server: accept failed: {}", ec.message());
            }
            continue;
        }

        beast::flat_buffer buffer;
        http::request<http::string_body> req;
        http::read(socket, buffer, req, ec);
        if (ec) {
            continue;
        }

        unsigned status = 200;
        const std::string body = handle_request(
            std::string(req.method_string()),
            std::string(req.target()),
            std::string(req[http::field::authorization]),
            req.body(),
            status
        );

        http::response<http::string_body> res{static_cast<http::status>(status), req.version()};
        res.set(http::field::server, "PrusaSlicer plugin server");
        res.set(http::field::content_type, "application/json");
        res.keep_alive(false);
        res.body() = body;
        res.prepare_payload();
        http::write(socket, res, ec);
        socket.shutdown(tcp::socket::shutdown_send, ec);
    }
}

std::string PluginServer::handle_request(
    const std::string& method,
    const std::string& target,
    const std::string& authorization,
    const std::string& body,
    unsigned& status
)
{
    nlohmann::json out;

    if (authorization != "Bearer " + m_token) {
        status = 401;
        out["ok"]    = false;
        out["error"] = "invalid or missing bearer token";
        return out.dump();
    }

    if (method == "GET" && target == "/ping") {
        out["ok"]      = true;
        out["version"] = SLIC3R_VERSION;
        return out.dump();
    }

    if (method == "POST" && target == "/lua") {
        std::string code;
        try {
            const auto j = nlohmann::json::parse(body);
            code         = j.value("code", std::string());
        } catch (const std::exception& e) {
            status       = 400;
            out["ok"]    = false;
            out["error"] = std::string("invalid JSON body: ") + e.what();
            return out.dump();
        }

        // Run on the main thread. The promise is shared so a timed-out request cannot dangle.
        auto promise = std::make_shared<std::promise<PluginSystem::ExecutionResult>>();
        auto future  = promise->get_future();
        auto& dispatcher = Biz::Platform::PlatformServices::instance().main_thread_dispatcher();
        const bool dispatched = dispatcher.dispatch_on_main_thread(
            [this, promise, code = std::move(code)]() mutable
            {
                try {
                    promise->set_value(m_plugin_system.execute_source(code, "=remote"));
                } catch (...) {
                    promise->set_exception(std::current_exception());
                }
            }
        );
        if (!dispatched) {
            status       = 503;
            out["ok"]    = false;
            out["error"] = "application is shutting down";
            return out.dump();
        }
        Biz::Platform::PlatformServices::instance().render_request_handler().request_render();

        if (future.wait_for(REQUEST_TIMEOUT) != std::future_status::ready) {
            status       = 504;
            out["ok"]    = false;
            out["error"] = "timed out waiting for the main thread";
            return out.dump();
        }
        try {
            const PluginSystem::ExecutionResult result = future.get();
            out["ok"]     = result.ok;
            out["output"] = result.output;
            out["result"] = result.result;
            out["error"]  = result.error;
        } catch (const std::exception& e) {
            status       = 500;
            out["ok"]    = false;
            out["error"] = e.what();
        }
        return out.dump();
    }

    status       = 404;
    out["ok"]    = false;
    out["error"] = "unknown endpoint, use GET /ping or POST /lua";
    return out.dump();
}

} // namespace Slic3r::App::Lua

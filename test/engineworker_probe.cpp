#include <chrono>
#include <iostream>
#include <string>
#include <thread>
#include <variant>

#include <nlohmann/json.hpp>

#include "engine/worker.h"

int main()
{
    using nlohmann::json;
    using namespace std::chrono_literals;
    const json input = json::parse(std::cin);
    Engine::Worker worker({input.at("url").get<std::string>(), input.at("username").get<std::string>(),
                           input.at("password").get<std::string>(), std::chrono::milliseconds(input.value("timeout", 3000))},
                          std::chrono::milliseconds(input.value("poll_ms", 10000)));
    std::size_t submitted = 0;
    if (input.contains("stop"))
    {
        worker.submit(Engine::Stop {Engine::TorrentId(input.at("stop").get<std::string>())});
        ++submitted;
    }
    std::cout << json {{"ready", true}, {"submitted", submitted}}.dump() << std::endl;
    json events = json::array();
    const auto deadline = std::chrono::steady_clock::now() + 5s;
    std::size_t settled = 0;
    bool snapshot = false;
    while (std::chrono::steady_clock::now() < deadline)
    {
        for (const Engine::Event &event : worker.takeEvents())
        {
            if (std::holds_alternative<Engine::Connected>(event))
                events.push_back({{"type", "connected"}});
            if (const Engine::Snapshot *value = std::get_if<Engine::Snapshot>(&event))
            {
                events.push_back({{"type", "snapshot"}, {"count", value->torrents.size()}});
                snapshot = true;
            }
            if (const Engine::Accepted *value = std::get_if<Engine::Accepted>(&event))
            {
                events.push_back({{"type", "accepted"}, {"id", value->requestId}});
                ++settled;
                snapshot = false;
            }
            if (const Engine::Failure *value = std::get_if<Engine::Failure>(&event))
            {
                events.push_back({{"type", "failure"}, {"id", value->requestId}, {"kind", static_cast<int>(value->kind)}, {"status", value->status}});
                if (value->requestId != 0)
                    ++settled;
            }
        }
        if (((settled == submitted) && snapshot) || worker.finished())
            break;
        std::this_thread::sleep_for(1ms);
    }
    worker.requestStop();
    std::cout << json {{"events", events}}.dump() << '\n';
}

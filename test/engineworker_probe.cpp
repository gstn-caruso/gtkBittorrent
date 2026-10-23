#include <algorithm>
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
    if (input.contains("start"))
    {
        worker.submit(Engine::Start {Engine::TorrentId(input.at("start").get<std::string>())});
        ++submitted;
    }
    if (input.value("stop_before_connect", false))
        worker.requestStop();
    std::cout << json {{"ready", true}, {"submitted", submitted}}.dump() << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(input.value("consumer_delay_ms", 0)));
    json events = json::array();
    const auto deadline = std::chrono::steady_clock::now() + 5s;
    std::size_t settled = 0;
    std::size_t maxBatchSnapshots = 0;
    bool snapshot = false;
    const auto collect = [&]()
    {
        std::size_t batchSnapshots = 0;
        for (const Engine::Event &event : worker.takeEvents())
        {
            if (std::holds_alternative<Engine::Connected>(event))
                events.push_back({{"type", "connected"}});
            if (const Engine::Snapshot *value = std::get_if<Engine::Snapshot>(&event))
            {
                events.push_back({{"type", "snapshot"}, {"count", value->torrents.size()}});
                snapshot = true;
                ++batchSnapshots;
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
                {
                    ++settled;
                    snapshot = false;
                }
            }
        }
        maxBatchSnapshots = std::max(maxBatchSnapshots, batchSnapshots);
    };
    while (std::chrono::steady_clock::now() < deadline)
    {
        collect();
        if (((settled == submitted) && snapshot) || worker.finished())
            break;
        std::this_thread::sleep_for(1ms);
    }
    worker.requestStop();
    while (!worker.finished() && (std::chrono::steady_clock::now() < (deadline + 6s)))
        std::this_thread::sleep_for(1ms);
    collect();
    std::cout << json {{"events", events}, {"max_batch_snapshots", maxBatchSnapshots}}.dump() << '\n';
}

#include <iostream>
#include <string>

#include <nlohmann/json.hpp>

#include "engine/client.h"

int main()
{
    using nlohmann::json;
    try
    {
        const json input = json::parse(std::cin);
        Engine::Client client(input.at("url").get<std::string>());
        client.login(input.at("username").get<std::string>(), input.at("password").get<std::string>());
        json torrents = json::array();
        for (const Engine::TorrentSnapshot &torrent : client.torrents())
        {
            torrents.push_back({{"hash", torrent.id.value()}, {"name", torrent.name}, {"size", torrent.size},
                               {"progress", torrent.progress}, {"state", torrent.state}});
        }
        std::cout << json {{"torrents", torrents}}.dump() << '\n';
    }
    catch (const Engine::Error &error)
    {
        std::cout << json {{"error", static_cast<int>(error.kind())}, {"status", error.status()}}.dump() << '\n';
        return 1;
    }
}

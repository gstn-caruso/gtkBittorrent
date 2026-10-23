#include <chrono>
#include <cstddef>
#include <fstream>
#include <iostream>
#include <iterator>
#include <span>
#include <string>

#include <nlohmann/json.hpp>

#include "engine/client.h"

int main()
{
    using nlohmann::json;
    try
    {
        const json input = json::parse(std::cin);
        Engine::Client client(input.at("url").get<std::string>(), std::chrono::milliseconds(input.value("timeout", 3000)));
        client.login(input.at("username").get<std::string>(), input.at("password").get<std::string>());
        if (input.contains("magnet"))
            client.addMagnet(input.at("magnet").get<std::string>(), input.at("save_path").get<std::string>(), input.value("stopped", true));
        if (input.contains("torrent"))
        {
            std::ifstream file(input.at("torrent").get<std::string>(), std::ios::binary);
            const std::string bytes {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
            client.addTorrent(std::as_bytes(std::span(bytes)), input.at("save_path").get<std::string>(), input.value("stopped", true));
        }
        if (input.contains("stop"))
            client.stop(Engine::TorrentId(input.at("stop").get<std::string>()));
        if (input.contains("start"))
            client.start(Engine::TorrentId(input.at("start").get<std::string>()));
        if (input.contains("remove"))
            client.remove(Engine::TorrentId(input.at("remove").get<std::string>()), input.value("delete_files", false));
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

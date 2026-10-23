#pragma once

#include <filesystem>

namespace GtkBittorrent
{
    void importProfile(const std::filesystem::path &source, const std::filesystem::path &target);
    void importProfileDirectories(const std::filesystem::path &config, const std::filesystem::path &data
        , const std::filesystem::path &target);
}

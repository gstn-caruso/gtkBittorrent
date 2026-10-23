#include <cstdlib>
#include <exception>
#include <filesystem>
#include <iostream>

#include "profileimporter.h"

#ifdef _WIN32
int wmain(const int argc, wchar_t *argv[])
#else
int main(const int argc, char *argv[])
#endif
{
    const bool separateDirectories = (argc == 6) && (std::filesystem::path(argv[1]) == "--config")
        && (std::filesystem::path(argv[3]) == "--data");
    if ((argc != 3) && !separateDirectories)
    {
        std::cerr << "Usage: gtkbittorrent-import <qBittorrent-profile> <new-gtkBittorrent-profile>\n";
        std::cerr << "   or: gtkbittorrent-import --config <config-dir> --data <data-dir> <new-profile>\n";
        return EXIT_FAILURE;
    }
    try
    {
        if (separateDirectories)
            GtkBittorrent::importProfileDirectories(std::filesystem::path(argv[2]), std::filesystem::path(argv[4]), std::filesystem::path(argv[5]));
        else
            GtkBittorrent::importProfile(std::filesystem::path(argv[1]), std::filesystem::path(argv[2]));
        std::cout << "Imported profile. The original profile has not been changed.\n";
        return EXIT_SUCCESS;
    }
    catch (const std::exception &error)
    {
        std::cerr << "Profile import failed: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}

#include "profileimporter.h"

#include <array>
#include <random>
#include <stdexcept>
#include <string>
#include <system_error>

#include "applicationidentity.h"

namespace
{
    namespace fs = std::filesystem;

    const std::array<const char *, 3> profileDirectories {"config", "data", "downloads"};

    bool isWithin(const fs::path &candidate, const fs::path &directory)
    {
        for (fs::path current = candidate; !current.empty(); current = current.parent_path())
        {
            if (fs::exists(current) && fs::equivalent(current, directory))
                return true;
            if (current == current.parent_path())
                break;
        }
        return false;
    }

    void validateEntry(const fs::path &entry)
    {
        const fs::file_status status = fs::symlink_status(entry);
        if (!fs::is_directory(status) && !fs::is_regular_file(status))
            throw std::runtime_error("Profile contains a symlink or a special file: " + entry.string());
    }

    void validateTree(const fs::path &directory)
    {
        validateEntry(directory);
        for (const auto &entry : fs::recursive_directory_iterator(directory))
            validateEntry(entry.path());
    }

    void copyTree(const fs::path &source, const fs::path &target)
    {
        fs::create_directory(target);
        fs::permissions(target, fs::perms::owner_all);
        for (const auto &entry : fs::recursive_directory_iterator(source))
        {
            validateEntry(entry.path());
            const fs::path destination = target / entry.path().lexically_relative(source);
            if (entry.is_directory())
            {
                fs::create_directory(destination);
                fs::permissions(destination, fs::perms::owner_all);
            }
            else
            {
                fs::copy(entry.path(), destination, fs::copy_options::copy_symlinks);
                validateEntry(destination);
                fs::permissions(destination, fs::perms::owner_read | fs::perms::owner_write, fs::perm_options::add);
                fs::last_write_time(destination, fs::last_write_time(entry.path()));
            }
        }
    }

    std::string settingsExtension(const fs::path &config)
    {
        std::string foundExtension;
        for (const std::string extension : {".conf", ".ini"})
        {
            for (const std::string stem : {"qBittorrent", "qBittorrent_new"})
            {
                const fs::path settings = config / (stem + extension);
                if (!fs::exists(fs::symlink_status(settings)))
                    continue;
                if (!foundExtension.empty() && (foundExtension != extension))
                    throw std::runtime_error("Profile contains ambiguous .conf and .ini settings.");
                if (!fs::is_regular_file(fs::symlink_status(settings)))
                    throw std::runtime_error("Settings must be regular files.");
                foundExtension = extension;
            }
        }
        if (foundExtension.empty())
            throw std::runtime_error("Configuration directory must contain qBittorrent.conf or qBittorrent.ini.");
        return foundExtension;
    }

    fs::path createStage(const fs::path &parent)
    {
        std::random_device random;
        for (int attempt = 0; attempt < 20; ++attempt)
        {
            const fs::path stage = parent / (".gtkBittorrent-import-" + std::to_string(random()));
            if (fs::create_directory(stage))
                return stage;
        }
        throw std::runtime_error("Cannot create a temporary import directory.");
    }

    void renameSettings(const fs::path &stage, const std::string &sourceExtension)
    {
#if defined(_WIN32) || defined(__APPLE__)
        const std::string targetExtension = ".ini";
#else
        const std::string targetExtension = ".conf";
#endif
        for (const std::string suffix : {"", "_new"})
        {
            const fs::path oldSettings = stage / "config" / ("qBittorrent" + suffix + sourceExtension);
            const fs::path newSettings = stage / "config" / (std::string(GtkBittorrent::applicationName) + suffix + targetExtension);
            if (fs::exists(newSettings))
                throw std::runtime_error("Source already contains gtkBittorrent settings.");
            if (fs::exists(oldSettings))
                fs::rename(oldSettings, newSettings);
        }
    }

    void importDirectories(const std::array<fs::path, 3> &sources, const fs::path &target)
    {
        const fs::path targetPath = fs::weakly_canonical(fs::absolute(target));
        if (fs::exists(fs::symlink_status(target)))
            throw std::runtime_error("Target profile already exists; import will not overwrite it.");
        const fs::path lockfile = sources[0] / "lockfile";
        if (fs::exists(fs::symlink_status(lockfile)))
            throw std::runtime_error("Source profile has a lockfile; close qBittorrent before importing.");
        for (const fs::path &entry : sources)
        {
            if (entry.empty() || !fs::exists(fs::symlink_status(entry)))
                continue;
            if (!fs::is_directory(fs::symlink_status(entry)))
                throw std::runtime_error("Profile entries must be directories.");
            if (isWithin(targetPath, fs::canonical(entry)))
                throw std::runtime_error("Source and target profiles must be separate directories.");
            validateTree(entry);
        }
        const std::string sourceExtension = settingsExtension(sources[0]);
        fs::create_directories(targetPath.parent_path());
        const fs::path stage = createStage(targetPath.parent_path());
        try
        {
            fs::permissions(stage, fs::perms::owner_all);
            for (std::size_t index = 0; index < sources.size(); ++index)
            {
                const fs::path &entry = sources[index];
                if (!entry.empty() && fs::exists(entry))
                    copyTree(entry, stage / profileDirectories[index]);
            }
            validateTree(stage);
            renameSettings(stage, sourceExtension);
            if (fs::exists(lockfile) || fs::exists(stage / "config" / "lockfile"))
                throw std::runtime_error("Source profile acquired a lockfile during import; import was cancelled.");
            if (fs::exists(fs::symlink_status(targetPath)))
                throw std::runtime_error("Target profile appeared during import; import was cancelled.");
            fs::rename(stage, targetPath);
        }
        catch (...)
        {
            std::error_code cleanupError;
            fs::remove_all(stage, cleanupError);
            throw;
        }
    }
}

void GtkBittorrent::importProfile(const std::filesystem::path &source, const std::filesystem::path &target)
{
    validateEntry(source);
    if (isWithin(fs::weakly_canonical(fs::absolute(target)), fs::canonical(source)))
        throw std::runtime_error("Source and target profiles must be separate directories.");
    importDirectories({source / "config", source / "data", source / "downloads"}, target);
}

void GtkBittorrent::importProfileDirectories(const std::filesystem::path &config, const std::filesystem::path &data
    , const std::filesystem::path &target)
{
    validateEntry(config);
    validateEntry(data);
    importDirectories({config, data, {}}, target);
}

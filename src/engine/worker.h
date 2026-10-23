#pragma once

#include <chrono>
#include <cstdint>
#include <memory>
#include <string>
#include <variant>
#include <vector>

#include "client.h"

namespace Engine
{
    struct Connection
    {
        std::string url;
        std::string username;
        std::string password;
        std::chrono::milliseconds timeout = std::chrono::seconds(3);
    };

    struct Stop
    {
        TorrentId id;
    };

    using Command = std::variant<Stop>;

    struct Connected {};

    struct Snapshot
    {
        std::vector<TorrentSnapshot> torrents;
    };

    struct Accepted
    {
        std::uint64_t requestId;
    };

    struct Failure
    {
        std::uint64_t requestId;
        ErrorKind kind;
        long status;
        std::string message;
    };

    using Event = std::variant<Connected, Snapshot, Accepted, Failure>;

    class Worker
    {
    public:
        explicit Worker(Connection connection, std::chrono::milliseconds pollInterval = std::chrono::seconds(1));
        ~Worker();
        Worker(const Worker &) = delete;
        Worker &operator=(const Worker &) = delete;

        std::uint64_t submit(Command command);
        std::vector<Event> takeEvents();
        void requestStop();
        bool finished() const noexcept;

    private:
        struct Impl;
        std::unique_ptr<Impl> m_impl;
    };
}

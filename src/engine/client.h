#pragma once

#include <chrono>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace Engine
{
    enum class ErrorKind
    {
        InvalidInput,
        Authentication,
        Transport,
        Protocol,
        Server
    };

    class Error final : public std::runtime_error
    {
    public:
        Error(ErrorKind kind, const std::string &message, long status = 0);
        ErrorKind kind() const noexcept;
        long status() const noexcept;

    private:
        ErrorKind m_kind;
        long m_status;
    };

    class TorrentId
    {
    public:
        explicit TorrentId(std::string value);
        const std::string &value() const noexcept;

    private:
        std::string m_value;
    };

    struct TorrentSnapshot
    {
        TorrentId id;
        std::string name;
        std::uint64_t size;
        double progress;
        std::string state;
    };

    class Client
    {
    public:
        explicit Client(const std::string &url, std::chrono::milliseconds timeout = std::chrono::seconds(3));
        ~Client();
        Client(const Client &) = delete;
        Client &operator=(const Client &) = delete;

        void login(const std::string &username, const std::string &password);
        std::vector<TorrentSnapshot> torrents();
        void start(const TorrentId &id);
        void stop(const TorrentId &id);
        void remove(const TorrentId &id, bool deleteFiles);

    private:
        struct Impl;
        std::unique_ptr<Impl> m_impl;
    };
}

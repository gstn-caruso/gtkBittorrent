#include "worker.h"

#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <optional>
#include <stop_token>
#include <thread>
#include <utility>

namespace Engine
{
    struct Worker::Impl
    {
        struct Request
        {
            std::uint64_t id;
            Command command;
        };

        Impl(Connection connection, std::chrono::milliseconds pollInterval);
        ~Impl();
        void run(std::stop_token stop);
        void post(Event event);
        void complete(const std::optional<Failure> &failure);
        void requestStop();

        Connection connection;
        std::chrono::milliseconds pollInterval;
        std::mutex mutex;
        std::condition_variable_any condition;
        std::deque<Request> pending;
        std::vector<Event> events;
        std::uint64_t nextId = 1;
        bool accepting = true;
        std::atomic<bool> finished = false;
        std::jthread thread;
    };

    Worker::Impl::Impl(Connection settings, const std::chrono::milliseconds interval)
        : connection {std::move(settings)}
        , pollInterval {interval}
    {
        if ((interval.count() < 1) || (interval > std::chrono::minutes(1)))
            throw Error(ErrorKind::InvalidInput, "Polling interval must be between 1 and 60000 milliseconds");
        thread = std::jthread([this](const std::stop_token stop) { run(stop); });
    }

    Worker::Impl::~Impl()
    {
        requestStop();
    }

    void Worker::Impl::requestStop()
    {
        const std::lock_guard lock {mutex};
        accepting = false;
        thread.request_stop();
        condition.notify_all();
    }

    void Worker::Impl::post(Event event)
    {
        const std::lock_guard lock {mutex};
        if (std::holds_alternative<Snapshot>(event))
            std::erase_if(events, [](const Event &item) { return std::holds_alternative<Snapshot>(item); });
        events.push_back(std::move(event));
    }

    void Worker::Impl::complete(const std::optional<Failure> &failure)
    {
        const std::lock_guard lock {mutex};
        accepting = false;
        for (const Request &request : pending)
        {
            events.push_back(Failure {request.id, failure ? failure->kind : ErrorKind::Cancelled,
                                     failure ? failure->status : 0, failure ? failure->message : "Engine worker stopped"});
        }
        pending.clear();
        finished.store(true);
    }

    void Worker::Impl::run(const std::stop_token stop)
    {
        std::optional<Failure> failure;
        try
        {
            Client client(connection.url, connection.timeout);
            client.login(connection.username, connection.password);
            if (!stop.stop_requested())
            {
                Snapshot initial {client.torrents()};
                post(Connected {});
                post(std::move(initial));
            }
            auto nextPoll = std::chrono::steady_clock::now() + pollInterval;
            while (!stop.stop_requested())
            {
                std::optional<Request> request;
                {
                    std::unique_lock lock {mutex};
                    condition.wait_until(lock, stop, nextPoll, [this]() { return !pending.empty(); });
                    if (stop.stop_requested())
                        break;
                    if (!pending.empty())
                    {
                        request.emplace(std::move(pending.front()));
                        pending.pop_front();
                    }
                }
                if (request)
                {
                    try
                    {
                        client.stop(std::get<Stop>(request->command).id);
                        post(Accepted {request->id});
                    }
                    catch (const Error &error)
                    {
                        post(Failure {request->id, error.kind(), error.status(), error.what()});
                        if ((error.kind() == ErrorKind::Authentication) || (error.kind() == ErrorKind::Transport)
                            || (error.kind() == ErrorKind::Protocol))
                        {
                            failure = Failure {0, error.kind(), error.status(), error.what()};
                            break;
                        }
                    }
                }
                if (!stop.stop_requested())
                    post(Snapshot {client.torrents()});
                nextPoll = std::chrono::steady_clock::now() + pollInterval;
            }
        }
        catch (const Error &error)
        {
            failure = Failure {0, error.kind(), error.status(), error.what()};
            post(*failure);
        }
        catch (const std::exception &)
        {
            failure = Failure {0, ErrorKind::Transport, 0, "Engine worker failed"};
            post(*failure);
        }
        complete(failure);
    }

    Worker::Worker(Connection connection, const std::chrono::milliseconds pollInterval)
        : m_impl {std::make_unique<Impl>(std::move(connection), pollInterval)}
    {
    }

    Worker::~Worker() = default;

    std::uint64_t Worker::submit(Command command)
    {
        const std::lock_guard lock {m_impl->mutex};
        if (!m_impl->accepting)
            throw Error(ErrorKind::InvalidInput, "Engine worker is stopping");
        const std::uint64_t id = m_impl->nextId++;
        m_impl->pending.push_back({id, std::move(command)});
        m_impl->condition.notify_all();
        return id;
    }

    std::vector<Event> Worker::takeEvents()
    {
        const std::lock_guard lock {m_impl->mutex};
        std::vector<Event> events;
        events.swap(m_impl->events);
        return events;
    }

    void Worker::requestStop()
    {
        m_impl->requestStop();
    }

    bool Worker::finished() const noexcept
    {
        return m_impl->finished.load();
    }
}

#include "client.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <utility>

#include <curl/curl.h>
#include <nlohmann/json.hpp>

namespace
{
    using Json = nlohmann::json;
    using CurlString = std::unique_ptr<char, decltype(&curl_free)>;

    class CurlRuntime
    {
    public:
        CurlRuntime();
        ~CurlRuntime();
    };

    CurlRuntime::CurlRuntime()
    {
        if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK)
            throw Engine::Error(Engine::ErrorKind::Transport, "Cannot initialize HTTP transport");
    }

    CurlRuntime::~CurlRuntime()
    {
        curl_global_cleanup();
    }

    void check(const CURLcode code)
    {
        if (code != CURLE_OK)
            throw Engine::Error(Engine::ErrorKind::Transport, "HTTP transport failed");
    }

    std::string baseUrl(const std::string &value)
    {
        const std::unique_ptr<CURLU, decltype(&curl_url_cleanup)> url(curl_url(), curl_url_cleanup);
        if (!url || value.find('\0') != std::string::npos
            || (curl_url_set(url.get(), CURLUPART_URL, value.c_str(), CURLU_DISALLOW_USER) != CURLUE_OK))
        {
            throw Engine::Error(Engine::ErrorKind::InvalidInput, "Invalid engine URL");
        }
        char *part = nullptr;
        if (curl_url_get(url.get(), CURLUPART_SCHEME, &part, 0) != CURLUE_OK)
            throw Engine::Error(Engine::ErrorKind::InvalidInput, "Missing engine URL scheme");
        const CurlString scheme(part, curl_free);
        if ((std::string(scheme.get()) != "http") && (std::string(scheme.get()) != "https"))
            throw Engine::Error(Engine::ErrorKind::InvalidInput, "Engine URLs must use HTTP or HTTPS");
        for (const CURLUPart component : {CURLUPART_QUERY, CURLUPART_FRAGMENT})
        {
            part = nullptr;
            const CURLUcode code = curl_url_get(url.get(), component, &part, 0);
            const CurlString unused(part, curl_free);
            if (code == CURLUE_OK)
                throw Engine::Error(Engine::ErrorKind::InvalidInput, "Engine URLs cannot contain a query or fragment");
        }
        part = nullptr;
        if (curl_url_get(url.get(), CURLUPART_URL, &part, 0) != CURLUE_OK)
            throw Engine::Error(Engine::ErrorKind::InvalidInput, "Invalid engine URL");
        const CurlString normalized(part, curl_free);
        std::string result(normalized.get());
        if (result.back() != '/')
            result += '/';
        return result;
    }

    std::string encode(const std::string &value)
    {
        if (value.size() > static_cast<std::size_t>(std::numeric_limits<int>::max()))
            throw Engine::Error(Engine::ErrorKind::InvalidInput, "Request field is too large");
        const CurlString result(curl_easy_escape(nullptr, value.data(), static_cast<int>(value.size())), curl_free);
        if (!result)
            throw Engine::Error(Engine::ErrorKind::Transport, "Cannot encode request");
        return result.get();
    }

    std::size_t receive(char *data, const std::size_t size, const std::size_t count, void *context) noexcept
    {
        constexpr std::size_t maxResponse = 64 * 1024 * 1024;
        std::string &response = *static_cast<std::string *>(context);
        if ((size != 1) || (count > (maxResponse - response.size())))
            return 0;
        try
        {
            response.append(data, count);
            return count;
        }
        catch (...)
        {
            return 0;
        }
    }
}

namespace Engine
{
    Error::Error(const ErrorKind kind, const std::string &message, const long status)
        : std::runtime_error(message)
        , m_kind(kind)
        , m_status(status)
    {
    }

    ErrorKind Error::kind() const noexcept
    {
        return m_kind;
    }

    long Error::status() const noexcept
    {
        return m_status;
    }

    TorrentId::TorrentId(std::string value)
        : m_value(std::move(value))
    {
        const auto isHex = [](const char character)
        {
            return ((character >= '0') && (character <= '9'))
                || ((character >= 'a') && (character <= 'f'));
        };
        if (((m_value.size() != 40) && (m_value.size() != 64))
            || !std::all_of(m_value.begin(), m_value.end(), isHex))
        {
            throw Error(ErrorKind::InvalidInput, "Invalid torrent identifier");
        }
    }

    const std::string &TorrentId::value() const noexcept
    {
        return m_value;
    }

    struct Client::Impl
    {
        Impl(const std::string &url, std::chrono::milliseconds timeout);
        std::string request(const std::string &resource, const std::optional<std::string> &body = std::nullopt);

        std::string url;
        std::chrono::milliseconds timeout;
        std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> handle;
    };

    Client::Impl::Impl(const std::string &endpoint, const std::chrono::milliseconds requestTimeout)
        : timeout(requestTimeout)
        , handle(nullptr, curl_easy_cleanup)
    {
        static const CurlRuntime runtime;
        if ((timeout.count() < 1) || (timeout > std::chrono::minutes(1)))
            throw Error(ErrorKind::InvalidInput, "Request timeout must be between 1 and 60000 milliseconds");
        url = baseUrl(endpoint);
        handle.reset(curl_easy_init());
        if (!handle)
            throw Error(ErrorKind::Transport, "Cannot create HTTP transport");
    }

    std::string Client::Impl::request(const std::string &resource, const std::optional<std::string> &body)
    {
        curl_easy_reset(handle.get());
        std::string response;
        const std::string destination = url + "api/v2/" + resource;
        check(curl_easy_setopt(handle.get(), CURLOPT_URL, destination.c_str()));
        check(curl_easy_setopt(handle.get(), CURLOPT_REFERER, url.c_str()));
        check(curl_easy_setopt(handle.get(), CURLOPT_PROTOCOLS_STR, "http,https"));
        check(curl_easy_setopt(handle.get(), CURLOPT_NOSIGNAL, 1L));
        check(curl_easy_setopt(handle.get(), CURLOPT_NOPROXY, "localhost,127.0.0.1,::1"));
        check(curl_easy_setopt(handle.get(), CURLOPT_TIMEOUT_MS, static_cast<long>(timeout.count())));
        check(curl_easy_setopt(handle.get(), CURLOPT_COOKIEFILE, ""));
        check(curl_easy_setopt(handle.get(), CURLOPT_WRITEFUNCTION, receive));
        check(curl_easy_setopt(handle.get(), CURLOPT_WRITEDATA, &response));
        if (body)
        {
            check(curl_easy_setopt(handle.get(), CURLOPT_POSTFIELDSIZE_LARGE, static_cast<curl_off_t>(body->size())));
            check(curl_easy_setopt(handle.get(), CURLOPT_COPYPOSTFIELDS, body->c_str()));
        }
        check(curl_easy_perform(handle.get()));
        long status = 0;
        check(curl_easy_getinfo(handle.get(), CURLINFO_RESPONSE_CODE, &status));
        if ((status == 401) || (status == 403))
            throw Error(ErrorKind::Authentication, "Engine authentication failed", status);
        if ((status >= 300) && (status < 400))
            throw Error(ErrorKind::Protocol, "Engine redirects are not supported", status);
        if ((status < 200) || (status >= 300))
            throw Error(ErrorKind::Server, "Engine rejected the request", status);
        return response;
    }

    Client::Client(const std::string &url, const std::chrono::milliseconds timeout)
        : m_impl(std::make_unique<Impl>(url, timeout))
    {
    }

    Client::~Client() = default;

    void Client::login(const std::string &username, const std::string &password)
    {
        check(curl_easy_setopt(m_impl->handle.get(), CURLOPT_COOKIELIST, "ALL"));
        const std::string response = m_impl->request("auth/login", "username=" + encode(username) + "&password=" + encode(password));
        if (!response.empty() && (response != "Ok."))
            throw Error(ErrorKind::Authentication, "Engine authentication failed", 200);
    }

    std::vector<TorrentSnapshot> Client::torrents()
    {
        const std::string response = m_impl->request("torrents/info");
        try
        {
            const Json items = Json::parse(response);
            if (!items.is_array())
                throw Error(ErrorKind::Protocol, "Expected a torrent list");
            std::vector<TorrentSnapshot> result;
            result.reserve(items.size());
            for (const Json &item : items)
            {
                if (!item.at("size").is_number_unsigned() || !item.at("progress").is_number())
                    throw Error(ErrorKind::Protocol, "Invalid torrent size or progress");
                const double progress = item.at("progress").get<double>();
                if (!std::isfinite(progress) || (progress < 0) || (progress > 1))
                    throw Error(ErrorKind::Protocol, "Invalid torrent progress");
                result.push_back({TorrentId(item.at("hash").get<std::string>()), item.at("name").get<std::string>(),
                                  item.at("size").get<std::uint64_t>(), progress, item.at("state").get<std::string>()});
            }
            return result;
        }
        catch (const Json::exception &)
        {
            throw Error(ErrorKind::Protocol, "Invalid engine response");
        }
        catch (const Error &error)
        {
            if (error.kind() == ErrorKind::InvalidInput)
                throw Error(ErrorKind::Protocol, "Invalid torrent identifier in engine response");
            throw;
        }
    }
}

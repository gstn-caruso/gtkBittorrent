#include <libtorrent/session.hpp>
#include <libtorrent/session_params.hpp>
#include <libtorrent/settings_pack.hpp>
#include <libtorrent/add_torrent_params.hpp>
#include <libtorrent/torrent_info.hpp>
#include <libtorrent/torrent_status.hpp>
#include <libtorrent/magnet_uri.hpp>
#include <libtorrent/create_torrent.hpp>
#include <libtorrent/bencode.hpp>
#include <libtorrent/read_resume_data.hpp>
#include <libtorrent/write_resume_data.hpp>
#include <libtorrent/alert_types.hpp>
#include <libtorrent/peer_info.hpp>
#include <nlohmann/json.hpp>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <chrono>
#include <algorithm>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>
#include <thread>
#include <csignal>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <poll.h>
#include <unistd.h>

namespace lt = libtorrent;
namespace fs = std::filesystem;
using json = nlohmann::json;
using Clock = std::chrono::steady_clock;
static volatile std::sig_atomic_t stopping = 0;
static void stop(int) { stopping = 1; }

struct Failure : std::runtime_error {
    std::string code;
    Failure(std::string c, std::string m) : std::runtime_error(m), code(std::move(c)) {}
};

static std::string hex(char const* data, std::size_t size) {
    constexpr char digits[] = "0123456789abcdef";
    std::string out;
    out.reserve(size * 2);
    for (std::size_t i = 0; i < size; ++i) {
        auto byte = static_cast<unsigned char>(data[i]);
        out += digits[byte >> 4]; out += digits[byte & 15];
    }
    return out;
}

static std::vector<char> unhex(std::string const& value) {
    if (value.size() % 2) throw Failure("checkpoint", "Resume data truncado");
    auto nibble = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        throw Failure("checkpoint", "Resume data inválido");
    };
    std::vector<char> out;
    for (std::size_t i = 0; i < value.size(); i += 2)
        out.push_back(static_cast<char>((nibble(value[i]) << 4) | nibble(value[i+1])));
    return out;
}

static void emit(json value) {
    value["v"] = 1;
    std::cout << value.dump(-1, ' ', false, json::error_handler_t::replace) << '\n' << std::flush;
}

static void atomic_write(fs::path const& path, std::string const& data) {
    auto temp = path.string() + ".tmp";
    int fd = ::open(temp.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    if (fd < 0) throw Failure("storage", "No se puede escribir " + temp + ": " + std::strerror(errno));
    std::size_t offset = 0;
    while (offset < data.size()) {
        auto size = ::write(fd, data.data() + offset, data.size() - offset);
        if (size < 0 && errno == EINTR) continue;
        if (size <= 0) { ::close(fd); ::unlink(temp.c_str()); throw Failure("storage", "No se pudo guardar: " + std::string(std::strerror(errno))); }
        offset += size;
    }
    if (::fsync(fd) < 0) { ::close(fd); ::unlink(temp.c_str()); throw Failure("storage", "Error al sincronizar el checkpoint"); }
    ::close(fd);
    fs::rename(temp, path);
    int dir = ::open(path.parent_path().c_str(), O_RDONLY | O_DIRECTORY);
    if (dir < 0 || ::fsync(dir) < 0) { if (dir >= 0) ::close(dir); throw Failure("storage", "No se pudo sincronizar el directorio"); }
    ::close(dir);
}

static std::string read_file(fs::path const& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw Failure("storage", "No se puede leer " + path.string());
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

static std::string destination(json const& params) {
    fs::path path(params.at("destination").get<std::string>());
    if (!path.is_absolute()) throw Failure("invalid_path", "El destino debe ser absoluto");
    fs::create_directories(path);
    auto probe = path / (".gtkbittorrent-write-" + std::to_string(::getpid()));
    int fd = ::open(probe.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) throw Failure("permission", "No se puede escribir en el destino");
    ::close(fd); fs::remove(probe);
    return path.lexically_normal().string();
}

static int nonnegative(json const& p, std::string const& key, int fallback = 0) {
    int value = p.value(key, fallback);
    if (value < 0) throw Failure("invalid_argument", key + " debe ser mayor o igual a cero");
    return value;
}

static std::vector<std::string> trackers(json const& params) {
    auto urls = params.value("trackers", std::vector<std::string>{});
    for (auto const& url : urls)
        if (!(url.starts_with("https://") || url.starts_with("http://") || url.starts_with("udp://")))
            throw Failure("invalid_tracker", "Tracker inválido: " + url);
    return urls;
}

struct Transfer {
    lt::torrent_handle handle;
    std::string category;
    bool staged = true;
    bool paused = false;
    std::string resume;
};

class Engine {
    fs::path state_;
    int lock_ = -1;
    std::unique_ptr<lt::session> session_;
    std::map<std::string, Transfer> transfers_;
    std::set<std::string> saving_;
    int next_ = 0;
    json limits_ = {{"download", 0}, {"upload", 0}, {"active_downloads", 3}, {"active_seeds", 5}};
    bool recovered_ = false;

    std::string id_for(lt::torrent_handle const& handle) const {
        for (auto const& [id, t] : transfers_) if (t.handle == handle) return id;
        return {};
    }

    Transfer& get(json const& p) {
        auto found = transfers_.find(p.at("torrent").get<std::string>());
        if (found == transfers_.end()) throw Failure("not_found", "Transferencia inexistente");
        return found->second;
    }

    void apply_limits() {
        lt::settings_pack settings;
        settings.set_int(lt::settings_pack::download_rate_limit, nonnegative(limits_, "download"));
        settings.set_int(lt::settings_pack::upload_rate_limit, nonnegative(limits_, "upload"));
        settings.set_int(lt::settings_pack::active_downloads, nonnegative(limits_, "active_downloads", 3));
        settings.set_int(lt::settings_pack::active_seeds, nonnegative(limits_, "active_seeds", 5));
        settings.set_int(lt::settings_pack::active_limit, nonnegative(limits_, "active_downloads", 3) + nonnegative(limits_, "active_seeds", 5));
        session_->apply_settings(settings);
    }

    void restore() {
        bool exists = false;
        for (auto const& path : {state_ / "checkpoint.json", state_ / "checkpoint.previous.json"}) {
            if (!fs::exists(path)) continue;
            exists = true;
            try {
                auto data = json::parse(read_file(path));
                if (data.at("schema") != 1) throw Failure("checkpoint", "Formato desconocido");
                std::vector<std::pair<json, lt::add_torrent_params>> pending;
                for (auto const& item : data.at("transfers")) {
                    auto bytes = unhex(item.at("resume").get<std::string>());
                    lt::error_code ec;
                    auto p = lt::read_resume_data(lt::span<char const>(bytes.data(), bytes.size()), ec);
                    if (ec || !p.ti) throw Failure("checkpoint", "No se pudo leer el estado de reanudación");
                    item.at("category").get<std::string>();
                    item.at("paused").get<bool>();
                    std::stoi(item.at("id").get<std::string>());
                    pending.emplace_back(item, std::move(p));
                }
                auto limits = data.at("limits");
                for (auto const& key : {"download", "upload", "active_downloads", "active_seeds"}) nonnegative(limits, key);
                limits_ = limits;
                for (auto& [item, p] : pending) {
                    auto id = item.at("id").get<std::string>();
                    bool paused = item.at("paused");
                    p.flags &= ~lt::torrent_flags::upload_mode;
                    if (paused) { p.flags &= ~lt::torrent_flags::auto_managed; p.flags |= lt::torrent_flags::paused; }
                    else { p.flags |= lt::torrent_flags::auto_managed; p.flags &= ~lt::torrent_flags::paused; }
                    auto handle = session_->add_torrent(std::move(p));
                    transfers_.emplace(id, Transfer{handle, item.at("category"), false, paused, item.at("resume")});
                    next_ = std::max(next_, std::stoi(id));
                }
                recovered_ = path.filename() == "checkpoint.previous.json";
                return;
            } catch (std::exception const& e) {
                std::cerr << path << ": " << e.what() << '\n';
                for (auto const& [id, t] : transfers_) session_->remove_torrent(t.handle);
                transfers_.clear();
            }
        }
        if (exists) throw Failure("checkpoint", "Ambos checkpoints están dañados. Restaure una copia antes de iniciar.");
    }

    void priorities(Transfer& t, json const& p) {
        if (!p.contains("priorities")) return;
        auto values = p.at("priorities").get<std::vector<int>>();
        auto ti = t.handle.torrent_file();
        if (!ti || values.size() != static_cast<std::size_t>(ti->num_files())) throw Failure("invalid_priorities", "Falta una prioridad por archivo");
        std::vector<lt::download_priority_t> result;
        for (int value : values) {
            if (value < 0 || value > 7) throw Failure("invalid_priorities", "Las prioridades deben estar entre 0 y 7");
            result.emplace_back(static_cast<std::uint8_t>(value));
        }
        t.handle.prioritize_files(result);
    }

    json summary(std::string const& id, Transfer const& t) const {
        auto s = t.handle.status();
        auto hashes = t.handle.info_hashes();
        auto remaining = std::max<std::int64_t>(0, s.total_wanted - s.total_wanted_done);
        return {{"id", id}, {"name", s.name}, {"category", t.category}, {"staged", t.staged}, {"paused", t.paused},
            {"queued", bool(s.flags & lt::torrent_flags::paused) && !t.paused && !t.staged},
            {"metadata", s.has_metadata}, {"progress", s.progress}, {"size", s.total_wanted}, {"done", s.total_wanted_done},
            {"download_rate", s.download_payload_rate}, {"upload_rate", s.upload_payload_rate}, {"peers", s.num_peers},
            {"eta", s.download_payload_rate > 0 ? remaining / s.download_payload_rate : -1},
            {"ratio", s.all_time_download > 0 ? double(s.all_time_upload) / s.all_time_download : 0.0},
            {"queue", static_cast<int>(s.queue_position)}, {"state", static_cast<int>(s.state)}, {"error", s.errc ? s.errc.message() : ""},
            {"destination", s.save_path}, {"download_limit", t.handle.download_limit()}, {"upload_limit", t.handle.upload_limit()},
            {"v1", hashes.has_v1() ? hex(hashes.v1.data(), 20) : ""}, {"v2", hashes.has_v2() ? hex(hashes.v2.data(), 32) : ""},
            {"magnet", s.has_metadata ? lt::make_magnet_uri(t.handle) : ""}};
    }

public:
    Engine(fs::path state, std::string const& listen, bool discovery) : state_(std::move(state)) {
        fs::create_directories(state_);
        ::chmod(state_.c_str(), 0700);
        lock_ = ::open((state_ / "engine.lock").c_str(), O_RDWR | O_CREAT | O_CLOEXEC, 0600);
        if (lock_ < 0 || ::flock(lock_, LOCK_EX | LOCK_NB) < 0) throw Failure("locked", "Este estado ya está en uso por otro motor");
        lt::settings_pack settings;
        settings.set_str(lt::settings_pack::listen_interfaces, listen);
        settings.set_str(lt::settings_pack::user_agent, "GtkBitTorrent/" APP_VERSION);
        settings.set_bool(lt::settings_pack::enable_dht, discovery);
        settings.set_bool(lt::settings_pack::enable_lsd, discovery);
        settings.set_bool(lt::settings_pack::enable_upnp, discovery);
        settings.set_bool(lt::settings_pack::enable_natpmp, discovery);
        settings.set_int(lt::settings_pack::alert_mask, lt::alert_category::error | lt::alert_category::storage | lt::alert_category::status);
        session_ = std::make_unique<lt::session>(settings);
        restore();
        apply_limits();
    }

    ~Engine() { session_.reset(); if (lock_ >= 0) ::close(lock_); }

    void alerts() {
        std::vector<lt::alert*> alerts;
        session_->pop_alerts(&alerts);
        for (auto* alert : alerts) {
            if (auto* a = lt::alert_cast<lt::save_resume_data_alert>(alert)) {
                auto id = id_for(a->handle);
                if (!id.empty()) {
                    auto bytes = lt::write_resume_data_buf(a->params);
                    transfers_.at(id).resume = hex(bytes.data(), bytes.size());
                    saving_.erase(id);
                }
            } else if (auto* a = lt::alert_cast<lt::save_resume_data_failed_alert>(alert)) {
                throw Failure("checkpoint", a->message());
            } else if (auto* a = lt::alert_cast<lt::metadata_received_alert>(alert)) {
                emit({{"event", "metadata"}, {"data", {{"torrent", id_for(a->handle)}}}});
            } else if (auto* a = lt::alert_cast<lt::storage_moved_alert>(alert)) {
                emit({{"event", "storage_moved"}, {"data", {{"torrent", id_for(a->handle)}, {"destination", a->storage_path()}}}});
            } else if (lt::alert_cast<lt::tracker_error_alert>(alert) || lt::alert_cast<lt::lsd_error_alert>(alert) ||
                       lt::alert_cast<lt::listen_failed_alert>(alert) || lt::alert_cast<lt::portmap_error_alert>(alert)) {
                emit({{"event", "network_warning"}, {"data", alert->message()}});
            } else if (alert->category() & lt::alert_category::error) {
                emit({{"event", "error"}, {"data", alert->message()}});
            }
        }
    }

    void checkpoint() {
        saving_.clear();
        for (auto const& [id, t] : transfers_) {
            if (t.staged) continue;
            saving_.insert(id);
            t.handle.save_resume_data(lt::torrent_handle::save_info_dict | lt::torrent_handle::flush_disk_cache);
        }
        auto deadline = Clock::now() + std::chrono::seconds(20);
        while (!saving_.empty() && Clock::now() < deadline) {
            session_->wait_for_alert(std::chrono::milliseconds(100));
            alerts();
        }
        if (!saving_.empty()) throw Failure("checkpoint", "Se agotó el tiempo para guardar el checkpoint");
        json data = {{"schema", 1}, {"limits", limits_}, {"transfers", json::array()}};
        for (auto const& [id, t] : transfers_) if (!t.staged)
            data["transfers"].push_back({{"id", id}, {"category", t.category}, {"paused", t.paused}, {"resume", t.resume}});
        auto path = state_ / "checkpoint.json";
        if (fs::exists(path) && !recovered_) atomic_write(state_ / "checkpoint.previous.json", read_file(path));
        atomic_write(path, data.dump());
        recovered_ = false;
    }

    json call(std::string const& method, json const& p) {
        if (method == "hello") return {{"version", APP_VERSION}, {"protocol", 1}, {"libtorrent", LIBTORRENT_VERSION}, {"recovered", recovered_}};
        if (method == "list") {
            json result = json::array();
            for (auto const& [id, t] : transfers_) result.push_back(summary(id, t));
            return result;
        }
        if (method == "settings") return limits_;
        if (method == "inspect") {
            lt::add_torrent_params params;
            auto source = p.at("source").get<std::string>();
            if (source.starts_with("magnet:?")) params = lt::parse_magnet_uri(source);
            else params.ti = std::make_shared<lt::torrent_info>(source);
            auto hashes = params.ti ? params.ti->info_hashes() : params.info_hashes;
            if (!hashes.has_v1() && !hashes.has_v2()) throw Failure("invalid_source", "El magnet no tiene un hash compatible");
            for (auto const& [id, t] : transfers_) {
                auto existing = t.handle.info_hashes();
                if ((hashes.has_v1() && existing.has_v1() && hashes.v1 == existing.v1) ||
                    (hashes.has_v2() && existing.has_v2() && hashes.v2 == existing.v2)) throw Failure("duplicate", "La transferencia ya existe (" + id + ")");
            }
            params.save_path = (state_ / "metadata").string();
            params.flags &= ~(lt::torrent_flags::paused | lt::torrent_flags::auto_managed);
            if (params.ti) params.flags |= lt::torrent_flags::paused;
            params.flags |= lt::torrent_flags::upload_mode | lt::torrent_flags::duplicate_is_error;
            auto handle = session_->add_torrent(std::move(params));
            auto id = std::to_string(++next_);
            transfers_.emplace(id, Transfer{handle, "", true, false, ""});
            return summary(id, transfers_.at(id));
        }
        if (method == "details") {
            auto& t = get(p);
            auto result = summary(p.at("torrent"), t);
            result["files"] = json::array(); result["trackers"] = json::array(); result["peers_detail"] = json::array();
            if (auto ti = t.handle.torrent_file()) {
                auto progress = t.handle.file_progress();
                auto priority = t.handle.get_file_priorities();
                for (auto index : ti->files().file_range()) {
                    int i = static_cast<int>(index);
                    result["files"].push_back({{"index", i}, {"path", ti->files().file_path(index)}, {"size", ti->files().file_size(index)},
                        {"done", progress.at(i)}, {"priority", static_cast<int>(priority.at(i))}, {"padding", ti->files().pad_file_at(index)}});
                }
            }
            for (auto const& tracker : t.handle.trackers()) {
                std::string error;
                for (auto const& endpoint : tracker.endpoints) for (auto const& hash : endpoint.info_hashes)
                    if (hash.last_error) error = hash.last_error.message();
                result["trackers"].push_back({{"url", tracker.url}, {"tier", tracker.tier}, {"error", error}});
            }
            std::vector<lt::peer_info> peers;
            t.handle.get_peer_info(peers);
            for (auto const& peer : peers) result["peers_detail"].push_back({{"address", peer.ip.address().to_string()}, {"port", peer.ip.port()},
                {"client", peer.client}, {"progress", peer.progress}, {"download_rate", peer.down_speed}, {"upload_rate", peer.up_speed}});
            return result;
        }
        if (method == "confirm") {
            auto& t = get(p);
            if (!t.staged) throw Failure("invalid_state", "La transferencia ya fue confirmada");
            if (!t.handle.status().has_metadata) throw Failure("metadata_pending", "Espere los metadatos del magnet");
            auto target = destination(p);
            auto category = p.value("category", std::string{});
            priorities(t, p);
            t.handle.move_storage(target);
            // Wait for the actual destination before making this transfer durable.
            auto deadline = Clock::now() + std::chrono::seconds(10);
            while (t.handle.status().save_path != target && Clock::now() < deadline) {
                std::this_thread::sleep_for(std::chrono::milliseconds(20)); alerts();
            }
            if (t.handle.status().save_path != target) throw Failure("storage", "No se pudo establecer el destino");
            t.category = category; t.staged = false;
            t.handle.unset_flags(lt::torrent_flags::upload_mode);
            t.handle.set_flags(lt::torrent_flags::auto_managed);
            t.handle.force_recheck();
            t.handle.resume();
        } else if (method == "remove") {
            auto& t = get(p);
            bool erase = p.value("delete_files", false);
            if (erase && !p.value("confirmed", false)) throw Failure("confirmation_required", "Confirme explícitamente el borrado de archivos");
            session_->remove_torrent(t.handle, erase ? lt::session::delete_files : lt::remove_flags_t{});
            transfers_.erase(p.at("torrent").get<std::string>());
        } else if (method == "pause" || method == "resume") {
            auto& t = get(p);
            if (t.staged) throw Failure("invalid_state", "Confirme la transferencia primero");
            t.paused = method == "pause";
            if (t.paused) { t.handle.unset_flags(lt::torrent_flags::auto_managed); t.handle.pause(); }
            else { t.handle.clear_error(); t.handle.set_flags(lt::torrent_flags::auto_managed); t.handle.resume(); }
        } else if (method == "recheck") { get(p).handle.force_recheck();
        } else if (method == "move") {
            auto& t = get(p);
            auto target = destination(p);
            t.handle.move_storage(target);
            auto deadline = Clock::now() + std::chrono::seconds(20);
            while (t.handle.status().save_path != target && Clock::now() < deadline) {
                std::this_thread::sleep_for(std::chrono::milliseconds(20)); alerts();
            }
            if (t.handle.status().save_path != target) throw Failure("storage", "No se pudo mover la transferencia");
        } else if (method == "priorities") { priorities(get(p), p);
        } else if (method == "category") { get(p).category = p.at("category").get<std::string>();
        } else if (method == "queue") {
            int position = nonnegative(p, "position");
            get(p).handle.queue_position_set(lt::queue_position_t(position));
        } else if (method == "limits") {
            auto down = nonnegative(p, "download"); auto up = nonnegative(p, "upload");
            if (p.contains("torrent")) { auto& t = get(p); t.handle.set_download_limit(down); t.handle.set_upload_limit(up); }
            else {
                nonnegative(p, "active_downloads", 3); nonnegative(p, "active_seeds", 5);
                limits_ = p; apply_limits();
            }
        } else if (method == "trackers") {
            auto urls = trackers(p);
            std::vector<lt::announce_entry> entries;
            for (auto const& url : urls) entries.emplace_back(url);
            get(p).handle.replace_trackers(entries); get(p).handle.force_reannounce();
        } else if (method == "connect_peer") {
            auto address = lt::make_address(p.at("address").get<std::string>());
            int port = p.at("port");
            if (port < 1 || port > 65535) throw Failure("invalid_port", "Puerto inválido");
            get(p).handle.connect_peer(lt::tcp::endpoint(address, static_cast<unsigned short>(port)));
            return true;
        } else if (method == "create") {
            fs::path source = fs::absolute(p.at("source").get<std::string>());
            if (!fs::exists(source) || fs::is_symlink(source)) throw Failure("invalid_path", "El origen no existe o es un enlace simbólico");
            if (fs::is_directory(source)) for (auto const& entry : fs::recursive_directory_iterator(source))
                if (entry.is_symlink()) throw Failure("invalid_path", "El origen contiene enlaces simbólicos");
            auto urls = trackers(p);
            auto format = p.value("format", std::string("v1"));
            if (format != "v1" && format != "v2" && format != "hybrid") throw Failure("invalid_format", "Use v1, v2 o hybrid");
            lt::file_storage files;
            lt::add_files(files, source.string());
            auto flags = format == "v1" ? lt::create_torrent::v1_only : format == "v2" ? lt::create_torrent::v2_only : lt::create_flags_t{};
            lt::create_torrent torrent(files, 0, flags);
            for (auto const& url : urls) torrent.add_tracker(url);
            torrent.set_creator("GtkBitTorrent/" APP_VERSION);
            torrent.set_priv(p.value("private", false));
            lt::set_piece_hashes(torrent, source.parent_path().string());
            std::vector<char> bytes;
            lt::bencode(std::back_inserter(bytes), torrent.generate());
            fs::path output(p.at("output").get<std::string>());
            if (!output.is_absolute() || fs::exists(output)) throw Failure("invalid_path", "El archivo de salida debe ser nuevo y absoluto");
            atomic_write(output, std::string(bytes.begin(), bytes.end()));
            lt::torrent_info info(output.string());
            return {{"output", output.string()}, {"magnet", lt::make_magnet_uri(info)}};
        } else if (method == "checkpoint" || method == "shutdown") {
            checkpoint(); if (method == "shutdown") stopping = 1; return true;
        } else throw Failure("unknown_method", "Método desconocido: " + method);
        checkpoint();
        return true;
    }
};

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--version") { std::cout << APP_VERSION << '\n'; return 0; }
    std::signal(SIGTERM, stop); std::signal(SIGINT, stop); std::signal(SIGPIPE, SIG_IGN);
    try {
        fs::path state;
        std::string listen = "0.0.0.0:6881,[::]:6881";
        bool discovery = true;
        for (int i = 1; i < argc; ++i) {
            std::string arg(argv[i]);
            if (i + 1 >= argc) throw Failure("arguments", "Falta el valor de " + arg);
            std::string value(argv[++i]);
            if (arg == "--state-dir") state = value;
            else if (arg == "--listen") listen = value;
            else if (arg == "--discovery") discovery = value != "false";
            else throw Failure("arguments", "Argumento desconocido: " + arg);
        }
        if (state.empty() || !state.is_absolute()) throw Failure("arguments", "--state-dir debe ser absoluto");
        Engine engine(state, listen, discovery);
        std::string buffer;
        auto checkpoint_at = Clock::now() + std::chrono::seconds(30);
        auto status_at = Clock::now();
        while (!stopping) {
            pollfd input{STDIN_FILENO, POLLIN, 0};
            int ready = ::poll(&input, 1, 100);
            if (ready > 0 && (input.revents & (POLLIN | POLLHUP))) {
                char bytes[8192]; auto size = ::read(STDIN_FILENO, bytes, sizeof(bytes));
                if (size <= 0) break;
                buffer.append(bytes, size);
                if (buffer.size() > 1024 * 1024) throw Failure("protocol", "Solicitud demasiado grande");
                std::size_t end;
                while ((end = buffer.find('\n')) != std::string::npos) {
                    auto line = buffer.substr(0, end); buffer.erase(0, end + 1);
                    json id = nullptr;
                    try {
                        auto request = json::parse(line);
                        id = request.at("id");
                        if (request.at("v") != 1) throw Failure("protocol_version", "Se requiere protocolo 1");
                        auto result = engine.call(request.at("method"), request.value("params", json::object()));
                        emit({{"id", id}, {"result", result}});
                    } catch (Failure const& e) { emit({{"id", id}, {"error", {{"code", e.code}, {"message", e.what()}}}});
                    } catch (std::exception const& e) { emit({{"id", id}, {"error", {{"code", "invalid_request"}, {"message", e.what()}}}}); }
                }
            }
            engine.alerts();
            if (Clock::now() >= status_at) { emit({{"event", "status"}, {"data", engine.call("list", json::object())}}); status_at = Clock::now() + std::chrono::seconds(1); }
            if (Clock::now() >= checkpoint_at) { engine.checkpoint(); checkpoint_at = Clock::now() + std::chrono::seconds(30); }
        }
        engine.checkpoint();
    } catch (std::exception const& e) { std::cerr << e.what() << '\n'; return 1; }
}

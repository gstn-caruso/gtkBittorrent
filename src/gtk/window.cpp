#include "window.h"

#include <algorithm>
#include <array>
#include <iomanip>
#include <sstream>
#include <string>
#include <utility>

namespace
{
    std::string stateText(const std::string &state)
    {
        if ((state == "stoppedDL") || (state == "stoppedUP") || (state == "pausedDL") || (state == "pausedUP"))
            return "Stopped";
        if ((state == "downloading") || (state == "forcedDL"))
            return "Downloading";
        if ((state == "uploading") || (state == "stalledUP") || (state == "forcedUP"))
            return "Seeding";
        if (state == "stalledDL")
            return "Waiting for peers";
        if ((state == "metaDL") || (state == "forcedMetaDL"))
            return "Getting metadata";
        if (state.starts_with("checking"))
            return "Checking";
        if (state.starts_with("queued"))
            return "Queued";
        if ((state == "error") || (state == "missingFiles"))
            return "Error";
        return "Unknown";
    }

    std::string byteText(const std::uint64_t bytes)
    {
        const std::array units {"B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"};
        double value = static_cast<double>(bytes);
        std::size_t unit = 0;
        while ((value >= 1024) && ((unit + 1) < units.size()))
        {
            value /= 1024;
            ++unit;
        }
        std::ostringstream text;
        text << std::fixed << std::setprecision(unit == 0 ? 0 : 1) << value << ' ' << units[unit];
        return text.str();
    }

    void setCellChild(const Glib::RefPtr<Glib::Object> &object, Gtk::Widget &child)
    {
        if (const auto item = std::dynamic_pointer_cast<Gtk::ListItem>(object))
            item->set_child(child);
        else if (const auto cell = std::dynamic_pointer_cast<Gtk::ColumnViewCell>(object))
            cell->set_child(child);
    }

    std::pair<Glib::RefPtr<Glib::ObjectBase>, Gtk::Widget *> cellContents(const Glib::RefPtr<Glib::Object> &object)
    {
        if (const auto item = std::dynamic_pointer_cast<Gtk::ListItem>(object))
            return {item->get_item(), item->get_child()};
        if (const auto cell = std::dynamic_pointer_cast<Gtk::ColumnViewCell>(object))
            return {cell->get_item(), cell->get_child()};
        return {};
    }

    Glib::RefPtr<Gtk::ColumnViewColumn> column(const char *title, const unsigned int field)
    {
        const auto factory = Gtk::SignalListItemFactory::create();
        factory->signal_setup_obj().connect([field](const Glib::RefPtr<Glib::Object> &object)
        {
            if (field == 2)
            {
                auto *progress = Gtk::make_managed<Gtk::ProgressBar>();
                progress->set_show_text(true);
                progress->set_margin(8);
                setCellChild(object, *progress);
            }
            else
            {
                auto *label = Gtk::make_managed<Gtk::Label>();
                label->set_xalign(field == 1 ? 1.0F : 0.0F);
                label->set_ellipsize(Pango::EllipsizeMode::END);
                label->set_margin(8);
                setCellChild(object, *label);
            }
        });
        factory->signal_bind_obj().connect([field](const Glib::RefPtr<Glib::Object> &object)
        {
            const auto [item, child] = cellContents(object);
            const auto row = std::dynamic_pointer_cast<Gui::TorrentRow>(item);
            if (!row)
                return;
            const Engine::TorrentSnapshot &torrent = row->snapshot();
            if (field == 2)
            {
                if (auto *progress = dynamic_cast<Gtk::ProgressBar *>(child))
                {
                    progress->set_fraction(torrent.progress);
                    progress->set_text(std::to_string(static_cast<int>(torrent.progress * 100)) + "%");
                }
            }
            else if (auto *label = dynamic_cast<Gtk::Label *>(child))
            {
                label->set_text(field == 0 ? torrent.name : (field == 1 ? byteText(torrent.size) : stateText(torrent.state)));
                if (field == 0)
                    label->set_tooltip_text(torrent.name);
            }
        });
        const auto result = Gtk::ColumnViewColumn::create(title, factory);
        result->set_expand(field == 0);
        result->set_resizable(true);
        result->set_fixed_width(field == 0 ? 350 : 150);
        return result;
    }
}

namespace Gui
{
    Window::Window()
        : m_title {"gtkBittorrent"}
        , m_root {Gtk::Orientation::VERTICAL}
        , m_addressLabel {"_Address", true}
        , m_usernameLabel {"_Username", true}
        , m_passwordLabel {"_Password", true}
        , m_connect {"Connect"}
        , m_toolbar {Gtk::Orientation::HORIZONTAL, 8}
        , m_addMagnet {"Add magnet…"}
        , m_start {"Start"}
        , m_stop {"Stop"}
        , m_footer {Gtk::Orientation::HORIZONTAL, 12}
        , m_status {"Enter your connection details, then choose Connect."}
        , m_count {"0 torrents"}
        , m_magnetDialog {*this}
        , m_rows {Gio::ListStore<TorrentRow>::create()}
        , m_selection {Gtk::SingleSelection::create(m_rows)}
    {
        set_title("gtkBittorrent — GTK preview");
        set_default_size(1050, 650);
        m_title.add_css_class("title");
        m_header.set_title_widget(m_title);
        set_titlebar(m_header);
        set_child(m_root);
        m_connection.set_margin(12);
        m_connection.set_row_spacing(4);
        m_connection.set_column_spacing(8);
        m_addressLabel.set_mnemonic_widget(m_address);
        m_usernameLabel.set_mnemonic_widget(m_username);
        m_passwordLabel.set_mnemonic_widget(m_password);
        for (Gtk::Label *label : {&m_addressLabel, &m_usernameLabel, &m_passwordLabel})
            label->set_xalign(0);
        m_connection.attach(m_addressLabel, 0, 0);
        m_connection.attach(m_usernameLabel, 1, 0);
        m_connection.attach(m_passwordLabel, 2, 0);
        m_connection.attach(m_address, 0, 1);
        m_connection.attach(m_username, 1, 1);
        m_connection.attach(m_password, 2, 1);
        m_connection.attach(m_connect, 3, 1);
        m_address.set_text("http://127.0.0.1:8080/");
        m_address.set_hexpand(true);
        m_username.set_text("admin");
        m_password.set_show_peek_icon(true);
        m_address.set_name("engine-address");
        m_username.set_name("engine-username");
        m_password.set_name("engine-password");
        m_connect.set_name("connect-engine");
        m_connect.add_css_class("suggested-action");
        m_connect.signal_clicked().connect(sigc::mem_fun(*this, &Window::connectEngine));
        m_start.set_name("start-torrent");
        m_stop.set_name("stop-torrent");
        m_start.signal_clicked().connect([this]() { submitSelected(true); });
        m_stop.signal_clicked().connect([this]() { submitSelected(false); });
        m_addMagnet.set_name("add-magnet");
        m_addMagnet.signal_clicked().connect([this]()
        {
            m_magnetDialog.reset();
            m_magnetDialog.present();
        });
        m_magnetDialog.signal_add().connect([this](Engine::AddMagnet command) { submit(std::move(command)); });
        m_toolbar.set_margin_start(12);
        m_toolbar.set_margin_end(12);
        m_toolbar.set_margin_bottom(8);
        m_toolbar.append(m_addMagnet);
        m_toolbar.append(m_start);
        m_toolbar.append(m_stop);
        m_selection->set_autoselect(false);
        m_selection->set_can_unselect(true);
        m_selectionChanged = m_selection->signal_selection_changed().connect([this](unsigned int, unsigned int) { updateControls(); });
        m_view.set_name("torrent-list");
        m_view.set_model(m_selection);
        m_view.add_css_class("data-table");
        m_view.set_show_row_separators(true);
        m_view.append_column(column("Name", 0));
        m_view.append_column(column("Size", 1));
        m_view.append_column(column("Progress", 2));
        m_view.append_column(column("State", 3));
        m_scroll.set_child(m_view);
        m_scroll.set_vexpand(true);
        m_footer.set_margin(12);
        m_status.set_xalign(0);
        m_status.set_name("connection-status");
        m_status.set_hexpand(true);
        m_count.set_xalign(1);
        m_footer.append(m_status);
        m_footer.append(m_count);
        m_root.append(m_connection);
        m_root.append(m_toolbar);
        m_root.append(m_scroll);
        m_root.append(m_footer);
        updateControls();
        m_timer = Glib::signal_timeout().connect(sigc::mem_fun(*this, &Window::poll), 50);
    }

    Window::~Window()
    {
        m_timer.disconnect();
        m_selectionChanged.disconnect();
        m_view.set_model({});
        if (m_worker)
            m_worker->requestStop();
        for (const auto &worker : m_retired)
            worker->requestStop();
    }

    void Window::connectEngine()
    {
        m_magnetDialog.hide();
        if (m_worker)
        {
            m_worker->requestStop();
            m_retired.push_back(std::move(m_worker));
        }
        m_connected = false;
        m_rows->remove_all();
        m_count.set_text("0 torrents");
        m_status.set_text("Connecting…");
        m_worker = std::make_unique<Engine::Worker>(Engine::Connection {m_address.get_text().raw(), m_username.get_text().raw(), m_password.get_text().raw()});
        updateControls();
    }

    void Window::submitSelected(const bool start)
    {
        const auto row = std::dynamic_pointer_cast<TorrentRow>(m_selection->get_selected_item());
        if (!m_worker || !m_connected || !row)
            return;
        if (start)
            submit(Engine::Start {row->snapshot().id});
        else
            submit(Engine::Stop {row->snapshot().id});
    }

    void Window::submit(Engine::Command command)
    {
        if (!m_worker || !m_connected)
            return;
        try
        {
            m_worker->submit(std::move(command));
        }
        catch (const Engine::Error &)
        {
            m_status.set_text("The connection has stopped. Choose Connect to try again.");
        }
    }

    void Window::updateControls()
    {
        const bool selected = static_cast<bool>(m_selection->get_selected_item());
        m_addMagnet.set_sensitive(m_connected);
        m_start.set_sensitive(m_connected && selected);
        m_stop.set_sensitive(m_connected && selected);
    }

    void Window::applySnapshot(const std::vector<Engine::TorrentSnapshot> &torrents)
    {
        const auto selected = std::dynamic_pointer_cast<TorrentRow>(m_selection->get_selected_item());
        const std::string id = selected ? selected->snapshot().id.value() : std::string();
        std::vector<Glib::RefPtr<TorrentRow>> rows;
        rows.reserve(torrents.size());
        for (const Engine::TorrentSnapshot &torrent : torrents)
            rows.push_back(TorrentRow::create(torrent));
        m_rows->splice(0, m_rows->get_n_items(), rows);
        for (unsigned int index = 0; index < rows.size(); ++index)
        {
            if (rows[index]->snapshot().id.value() == id)
                m_selection->set_selected(index);
        }
        m_count.set_text(std::to_string(torrents.size()) + (torrents.size() == 1 ? " torrent" : " torrents"));
        updateControls();
    }

    bool Window::poll()
    {
        std::erase_if(m_retired, [](const auto &worker) { return worker->finished(); });
        if (!m_worker)
            return true;
        for (const Engine::Event &event : m_worker->takeEvents())
        {
            if (std::holds_alternative<Engine::Connected>(event))
            {
                m_connected = true;
                m_status.set_text("Connected");
            }
            if (const Engine::Snapshot *snapshot = std::get_if<Engine::Snapshot>(&event))
                applySnapshot(snapshot->torrents);
            if (const Engine::Failure *failure = std::get_if<Engine::Failure>(&event))
            {
                m_status.set_text(failure->kind == Engine::ErrorKind::Authentication
                                     ? "Could not sign in. Check your username and password."
                                     : "The operation failed. Check the engine address and connection.");
            }
        }
        if (m_worker->finished())
        {
            m_connected = false;
            m_magnetDialog.hide();
        }
        updateControls();
        return true;
    }
}

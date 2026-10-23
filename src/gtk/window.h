#pragma once

#include <memory>
#include <vector>

#include <gtkmm.h>

#include "engine/worker.h"
#include "torrentrow.h"

namespace Gui
{
    class Window final : public Gtk::ApplicationWindow
    {
    public:
        Window();
        ~Window() override;

    private:
        void connectEngine();
        void submitSelected(bool start);
        void updateControls();
        void applySnapshot(const std::vector<Engine::TorrentSnapshot> &torrents);
        bool poll();

        Gtk::HeaderBar m_header;
        Gtk::Label m_title;
        Gtk::Box m_root;
        Gtk::Grid m_connection;
        Gtk::Label m_addressLabel;
        Gtk::Label m_usernameLabel;
        Gtk::Label m_passwordLabel;
        Gtk::Entry m_address;
        Gtk::Entry m_username;
        Gtk::PasswordEntry m_password;
        Gtk::Button m_connect;
        Gtk::Box m_toolbar;
        Gtk::Button m_start;
        Gtk::Button m_stop;
        Gtk::ScrolledWindow m_scroll;
        Gtk::ColumnView m_view;
        Gtk::Box m_footer;
        Gtk::Label m_status;
        Gtk::Label m_count;
        Glib::RefPtr<Gio::ListStore<TorrentRow>> m_rows;
        Glib::RefPtr<Gtk::SingleSelection> m_selection;
        std::unique_ptr<Engine::Worker> m_worker;
        std::vector<std::unique_ptr<Engine::Worker>> m_retired;
        sigc::connection m_timer;
        bool m_connected = false;
    };
}

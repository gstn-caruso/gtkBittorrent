#pragma once

#include <optional>

#include <gtkmm.h>

#include "engine/worker.h"

namespace Gui
{
    class RemovalDialog final : public Gtk::Window
    {
    public:
        explicit RemovalDialog(Gtk::Window &parent);
        void prepare(const Engine::TorrentSnapshot &torrent);
        sigc::signal<void(Engine::Remove)> &signal_remove();

    private:
        void submit();

        Gtk::Box m_root;
        Gtk::Label m_question;
        Gtk::Label m_name;
        Gtk::Label m_hint;
        Gtk::CheckButton m_deleteFiles;
        Gtk::Box m_actions;
        Gtk::Button m_cancel;
        Gtk::Button m_remove;
        std::optional<Engine::TorrentId> m_id;
        sigc::signal<void(Engine::Remove)> m_removeSignal;
    };
}

#pragma once

#include <gtkmm.h>

#include "engine/worker.h"

namespace Gui
{
    class MagnetDialog final : public Gtk::Window
    {
    public:
        explicit MagnetDialog(Gtk::Window &parent);
        void reset();
        sigc::signal<void(Engine::AddMagnet)> &signal_add();

    private:
        void submit();

        Gtk::Box m_root;
        Gtk::Label m_linkLabel;
        Gtk::Entry m_link;
        Gtk::Label m_pathLabel;
        Gtk::Entry m_path;
        Gtk::Label m_pathHint;
        Gtk::CheckButton m_stopped;
        Gtk::Label m_error;
        Gtk::Box m_actions;
        Gtk::Button m_cancel;
        Gtk::Button m_add;
        sigc::signal<void(Engine::AddMagnet)> m_addSignal;
    };
}

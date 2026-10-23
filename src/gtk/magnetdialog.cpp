#include "magnetdialog.h"

#include <string>

namespace Gui
{
    MagnetDialog::MagnetDialog(Gtk::Window &parent)
        : m_root {Gtk::Orientation::VERTICAL, 8}
        , m_linkLabel {"_Magnet link", true}
        , m_pathLabel {"_Destination on the engine", true}
        , m_pathHint {"Leave blank to use the engine's default download folder."}
        , m_stopped {"Add in _stopped state", true}
        , m_error {"Enter a magnet link starting with magnet:?."}
        , m_actions {Gtk::Orientation::HORIZONTAL, 8}
        , m_cancel {"Cancel"}
        , m_add {"Add magnet"}
    {
        set_title("Add magnet");
        set_name("add-magnet-dialog");
        set_default_size(560, -1);
        set_transient_for(parent);
        set_modal(true);
        set_hide_on_close(true);
        set_child(m_root);
        m_root.set_margin(16);
        m_linkLabel.set_xalign(0);
        m_linkLabel.set_mnemonic_widget(m_link);
        m_link.set_name("magnet-link");
        m_link.set_placeholder_text("magnet:?xt=urn:btih:…");
        m_link.set_activates_default(true);
        m_pathLabel.set_xalign(0);
        m_pathLabel.set_mnemonic_widget(m_path);
        m_path.set_name("save-path");
        m_path.set_activates_default(true);
        m_pathHint.set_xalign(0);
        m_pathHint.set_wrap(true);
        m_pathHint.add_css_class("dim-label");
        m_stopped.set_name("add-stopped");
        m_error.set_xalign(0);
        m_error.set_wrap(true);
        m_error.add_css_class("error");
        m_cancel.set_name("cancel-addition");
        m_cancel.signal_clicked().connect([this]() { hide(); });
        m_add.set_name("confirm-addition");
        m_add.add_css_class("suggested-action");
        m_add.signal_clicked().connect(sigc::mem_fun(*this, &MagnetDialog::submit));
        set_default_widget(m_add);
        m_actions.set_halign(Gtk::Align::END);
        m_actions.set_margin_top(8);
        m_actions.append(m_cancel);
        m_actions.append(m_add);
        m_root.append(m_linkLabel);
        m_root.append(m_link);
        m_root.append(m_pathLabel);
        m_root.append(m_path);
        m_root.append(m_pathHint);
        m_root.append(m_stopped);
        m_root.append(m_error);
        m_root.append(m_actions);
        reset();
    }

    void MagnetDialog::reset()
    {
        m_link.set_text("");
        m_path.set_text("");
        m_stopped.set_active(false);
        m_error.hide();
        set_focus(m_link);
    }

    sigc::signal<void(Engine::AddMagnet)> &MagnetDialog::signal_add()
    {
        return m_addSignal;
    }

    void MagnetDialog::submit()
    {
        const std::string magnet = m_link.get_text().raw();
        if (!magnet.starts_with("magnet:?") || (magnet.find_first_of("\r\n") != std::string::npos))
        {
            m_error.show();
            m_link.grab_focus();
            return;
        }
        m_addSignal.emit(Engine::AddMagnet {magnet, m_path.get_text().raw(), m_stopped.get_active()});
        hide();
    }
}

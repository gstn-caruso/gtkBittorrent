#include "removaldialog.h"

namespace Gui
{
    RemovalDialog::RemovalDialog(Gtk::Window &parent)
        : m_root {Gtk::Orientation::VERTICAL, 12}
        , m_question {"Remove this torrent?"}
        , m_hint {"Downloaded files are kept unless you choose to delete them."}
        , m_deleteFiles {"Also _delete downloaded files", true}
        , m_actions {Gtk::Orientation::HORIZONTAL, 8}
        , m_cancel {"Cancel"}
        , m_remove {"Remove"}
    {
        set_title("Remove torrent");
        set_name("remove-torrent-dialog");
        set_default_size(480, -1);
        set_transient_for(parent);
        set_modal(true);
        set_hide_on_close(true);
        set_child(m_root);
        m_root.set_margin(16);
        m_question.add_css_class("heading");
        for (Gtk::Label *label : {&m_question, &m_name, &m_hint})
        {
            label->set_xalign(0);
            label->set_wrap(true);
            label->set_max_width_chars(60);
        }
        m_name.set_selectable(true);
        m_hint.add_css_class("dim-label");
        m_deleteFiles.set_name("delete-files");
        m_cancel.set_name("cancel-removal");
        m_cancel.signal_clicked().connect([this]() { hide(); });
        m_remove.set_name("confirm-removal");
        m_remove.add_css_class("destructive-action");
        m_remove.signal_clicked().connect(sigc::mem_fun(*this, &RemovalDialog::submit));
        set_default_widget(m_cancel);
        m_actions.set_halign(Gtk::Align::END);
        m_actions.set_margin_top(8);
        m_actions.append(m_cancel);
        m_actions.append(m_remove);
        m_root.append(m_question);
        m_root.append(m_name);
        m_root.append(m_hint);
        m_root.append(m_deleteFiles);
        m_root.append(m_actions);
    }

    void RemovalDialog::prepare(const Engine::TorrentSnapshot &torrent)
    {
        m_id = torrent.id;
        m_name.set_text(torrent.name);
        m_deleteFiles.set_active(false);
        set_focus(m_cancel);
    }

    sigc::signal<void(Engine::Remove)> &RemovalDialog::signal_remove()
    {
        return m_removeSignal;
    }

    void RemovalDialog::submit()
    {
        if (!m_id)
            return;
        m_removeSignal.emit(Engine::Remove {*m_id, m_deleteFiles.get_active()});
        m_id.reset();
        hide();
    }
}

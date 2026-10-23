#include <chrono>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

#include <gtkmm.h>
#include <nlohmann/json.hpp>

#include "gtk/torrentrow.h"
#include "gtk/window.h"

namespace
{
    Gtk::Widget *find(Gtk::Widget &root, const Glib::ustring &name)
    {
        if (root.get_name() == name)
            return &root;
        for (Gtk::Widget *child : root.get_children())
        {
            if (Gtk::Widget *result = find(*child, name))
                return result;
        }
        return nullptr;
    }

    template <typename Widget>
    Widget &widget(Gtk::Widget &root, const char *name)
    {
        Widget *result = dynamic_cast<Widget *>(find(root, name));
        if (!result)
            throw std::runtime_error(std::string("Missing GTK widget: ") + name);
        return *result;
    }

    bool displays(Gtk::Widget &root, const Glib::ustring &text)
    {
        if (const auto *label = dynamic_cast<Gtk::Label *>(&root); label && (label->get_text() == text))
            return true;
        for (Gtk::Widget *child : root.get_children())
        {
            if (displays(*child, text))
                return true;
        }
        return false;
    }
}

int main(int argc, char **argv)
{
    using nlohmann::json;
    const json input = json::parse(std::cin);
    auto application = Gtk::Application::create("io.github.gstn_caruso.gtkBittorrent.GtkTests");
    std::unique_ptr<Gui::Window> window;
    sigc::connection timer;
    int phase = 0;
    bool passed = false;
    std::string failure;
    auto closeAt = std::chrono::steady_clock::time_point::max();
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(15);
    application->signal_activate().connect([&]()
    {
        window = std::make_unique<Gui::Window>();
        application->add_window(*window);
        window->present();
        widget<Gtk::Entry>(*window, "engine-address").set_text(input.at("url").get<std::string>());
        widget<Gtk::Entry>(*window, "engine-username").set_text(input.at("username").get<std::string>());
        widget<Gtk::PasswordEntry>(*window, "engine-password").set_text(input.at("password").get<std::string>());
        widget<Gtk::Button>(*window, "connect-engine").activate();
        timer = Glib::signal_timeout().connect([&]()
        {
            if (passed)
            {
                if (std::chrono::steady_clock::now() >= closeAt)
                {
                    window->close();
                    return false;
                }
                return true;
            }
            try
            {
                if (input.value("expect_auth_failure", false)
                    && displays(*window, "Could not sign in. Check your username and password."))
                {
                    if (widget<Gtk::Button>(*window, "start-torrent").get_sensitive()
                        || widget<Gtk::Button>(*window, "stop-torrent").get_sensitive())
                    {
                        throw std::runtime_error("Torrent controls remained enabled after authentication failed");
                    }
                    passed = true;
                    closeAt = std::chrono::steady_clock::now();
                    return true;
                }
                auto &view = widget<Gtk::ColumnView>(*window, "torrent-list");
                const auto selection = std::dynamic_pointer_cast<Gtk::SingleSelection>(view.get_model());
                if (selection && (selection->get_n_items() == input.value("count", 2U)))
                {
                    for (unsigned int index = 0; index < selection->get_n_items(); ++index)
                    {
                        const auto row = std::dynamic_pointer_cast<Gui::TorrentRow>(selection->get_object(index));
                        if (!row || (row->snapshot().id.value() != input.at("hash").get<std::string>()))
                            continue;
                        if (phase == 0)
                        {
                            if (!displays(*window, input.at("name").get<std::string>()))
                                continue;
                            selection->set_selected(index);
                            widget<Gtk::Button>(*window, "start-torrent").activate();
                            phase = 1;
                        }
                        else if ((phase == 1) && (row->snapshot().state == input.value("started_state", "downloading"))
                                 && (row->snapshot().progress == input.value("progress", 0.5)))
                        {
                            widget<Gtk::Button>(*window, "stop-torrent").activate();
                            phase = 2;
                        }
                        else if ((phase == 2) && (row->snapshot().state == "stoppedDL"))
                        {
                            passed = true;
                            closeAt = std::chrono::steady_clock::now() + std::chrono::milliseconds(input.value("hold_ms", 0));
                            return true;
                        }
                    }
                }
                if (std::chrono::steady_clock::now() >= deadline)
                    throw std::runtime_error("GTK controls did not reach the expected engine state");
            }
            catch (const std::exception &error)
            {
                failure = error.what();
                window->close();
                return false;
            }
            return true;
        }, 20);
    });
    application->run(argc, argv);
    timer.disconnect();
    window.reset();
    std::cout << json {{"passed", passed}, {"failure", failure}, {"phase", phase}}.dump() << '\n';
    return passed ? 0 : 1;
}

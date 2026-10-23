#include <memory>

#include <gtkmm/application.h>

#include "window.h"

int main(int argc, char **argv)
{
    auto application = Gtk::Application::create("io.github.gstn_caruso.gtkBittorrent.GtkPreview");
    std::unique_ptr<Gui::Window> window;
    application->signal_activate().connect([&]()
    {
        if (!window)
        {
            window = std::make_unique<Gui::Window>();
            application->add_window(*window);
        }
        window->present();
    });
    const int result = application->run(argc, argv);
    window.reset();
    return result;
}

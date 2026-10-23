#pragma once

#include <glibmm/object.h>

#include "engine/client.h"

namespace Gui
{
    class TorrentRow final : public Glib::Object
    {
    public:
        static Glib::RefPtr<TorrentRow> create(Engine::TorrentSnapshot snapshot);
        const Engine::TorrentSnapshot &snapshot() const;

    private:
        explicit TorrentRow(Engine::TorrentSnapshot snapshot);
        Engine::TorrentSnapshot m_snapshot;
    };
}

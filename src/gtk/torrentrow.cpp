#include "torrentrow.h"

#include <utility>

namespace Gui
{
    TorrentRow::TorrentRow(Engine::TorrentSnapshot snapshot)
        : Glib::ObjectBase {typeid(TorrentRow)}
        , m_snapshot {std::move(snapshot)}
    {
    }

    Glib::RefPtr<TorrentRow> TorrentRow::create(Engine::TorrentSnapshot snapshot)
    {
        return Glib::make_refptr_for_instance<TorrentRow>(new TorrentRow(std::move(snapshot)));
    }

    const Engine::TorrentSnapshot &TorrentRow::snapshot() const
    {
        return m_snapshot;
    }
}

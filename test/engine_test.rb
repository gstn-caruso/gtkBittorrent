require_relative "test_helper"

class ProtocolTest < EngineTest
  def test_invalid_requests_do_not_kill_engine
    client = engine
    error = assert_raises(GtkBitTorrent::EngineError) { client.request("no_such_method") }
    assert_equal "unknown_method", error.code
    assert_raises(GtkBitTorrent::EngineError) { client.request("inspect", {"source" => "magnet:?dn=bad"}) }
    assert_raises(GtkBitTorrent::EngineError) { client.request("limits", {"download" => -1}) }
    assert_equal [], client.request("list")
    assert_equal 1, client.request("hello")["protocol"]
  end

  def test_priorities_limits_trackers_queue_and_recovery
    client = engine
    _, torrent = fixture(client)
    id = inspect_torrent(client, torrent)
    assert client.request("details", {"torrent" => id})["staged"]
    confirm(client, id)
    client.request("priorities", {"torrent" => id, "priorities" => [7]})
    client.request("category", {"torrent" => id, "category" => "Linux"})
    client.request("limits", {"torrent" => id, "download" => 8192, "upload" => 4096})
    client.request("limits", {"download" => 16384, "upload" => 8192, "active_downloads" => 2, "active_seeds" => 3})
    client.request("trackers", {"torrent" => id, "trackers" => ["http://127.0.0.1:1/announce"]})
    client.request("queue", {"torrent" => id, "position" => 0})
    client.request("pause", {"torrent" => id})
    client.close
    @engines.delete(client)
    recovered = engine
    row = recovered.request("details", {"torrent" => id})
    assert row["paused"]
    assert_equal "Linux", row["category"]
    assert_equal 8192, row["download_limit"]
    assert_equal 7, row["files"][0]["priority"]
    assert_equal "http://127.0.0.1:1/announce", row["trackers"][0]["url"]
    assert_equal 2, recovered.request("settings")["active_downloads"]
    recovered.request("resume", {"torrent" => id})
    refute recovered.request("list")[0]["paused"]
  end

  def test_duplicates_and_torrent_formats
    client = engine
    %w[v1 v2 hybrid].each do |format|
      _, torrent = fixture(client, format: format, name: format)
      id = inspect_torrent(client, torrent)
      row = client.request("details", {"torrent" => id})
      assert_equal(format != "v2", !row["v1"].empty?)
      assert_equal(format != "v1", !row["v2"].empty?)
      assert_equal "duplicate", assert_raises(GtkBitTorrent::EngineError) { inspect_torrent(client, torrent) }.code
      assert_equal "duplicate", assert_raises(GtkBitTorrent::EngineError) { inspect_torrent(client, row["magnet"]) }.code
    end
  end

  def test_default_creation_is_v1_and_never_overwrites_output
    client = engine
    source = File.join(@dir, "source")
    File.write(source, "hello")
    output = File.join(@dir, "default.torrent")
    params = {"source" => source, "output" => output}
    client.request("create", params)
    row = client.request("details", {"torrent" => inspect_torrent(client, output)})
    refute_empty row["v1"]
    assert_empty row["v2"]
    assert_raises(GtkBitTorrent::EngineError) { client.request("create", params) }
  end

  def test_deleting_keeps_files_unless_explicitly_confirmed
    client = engine
    source, torrent = fixture(client)
    id = inspect_torrent(client, torrent)
    confirm(client, id)
    error = assert_raises(GtkBitTorrent::EngineError) { client.request("remove", {"torrent" => id, "delete_files" => true}) }
    assert_equal "confirmation_required", error.code
    client.request("remove", {"torrent" => id})
    assert File.exist?(source)
    assert_empty client.request("list")
  end

  def test_checkpoint_fallback_preserves_last_valid_state
    client = engine
    _, torrent = fixture(client)
    id = inspect_torrent(client, torrent)
    confirm(client, id)
    client.request("pause", {"torrent" => id})
    client.close
    @engines.delete(client)
    path = File.join(@dir, "state/checkpoint.json")
    File.write(path, "broken")
    recovered = engine
    assert recovered.request("hello")["recovered"]
    assert_equal id, recovered.request("list")[0]["id"]
    recovered.request("checkpoint")
    assert_equal 1, JSON.parse(File.read(path))["schema"]
  end

  def test_invalid_destination_and_file_priorities
    client = engine
    _, torrent = fixture(client)
    id = inspect_torrent(client, torrent)
    assert_raises(GtkBitTorrent::EngineError) { confirm(client, id, "/proc/gtkb-no-write") }
    assert client.request("details", {"torrent" => id})["staged"]
    assert_raises(GtkBitTorrent::EngineError) { client.request("confirm", {"torrent" => id, "destination" => @dir, "priorities" => [9]}) }
    assert client.request("details", {"torrent" => id})["staged"]
  end

  def test_engine_crash_recovers_confirmed_transfers
    client = engine
    _, torrent = fixture(client)
    id = inspect_torrent(client, torrent)
    confirm(client, id)
    client.request("pause", {"torrent" => id})
    Process.kill("KILL", client.instance_variable_get(:@wait).pid)
    client.instance_variable_get(:@wait).join
    assert_raises(GtkBitTorrent::EngineError) { client.request("list") }
    client.close
    @engines.delete(client)
    recovered = engine
    assert_equal id, recovered.request("list")[0]["id"]
    assert recovered.request("list")[0]["paused"]
  end

  def test_full_disk_does_not_replace_the_valid_checkpoint
    client = engine
    client.request("checkpoint")
    path = File.join(@dir, "state/checkpoint.json")
    before = File.read(path)
    # /dev/full deterministically returns ENOSPC, without filling the host disk.
    File.symlink("/dev/full", "#{path}.tmp")
    error = assert_raises(GtkBitTorrent::EngineError) { client.request("checkpoint") }
    assert_equal "storage", error.code
    assert_equal before, File.read(path)
    assert_equal [], client.request("list")
  end

  def test_both_corrupt_checkpoints_fail_without_overwriting_them
    state = File.join(@dir, "corrupt")
    FileUtils.mkdir_p(state)
    %w[checkpoint.json checkpoint.previous.json].each { |name| File.write(File.join(state, name), "broken") }
    assert_raises(GtkBitTorrent::EngineError) { engine("corrupt") }
    assert_equal "broken", File.read(File.join(state, "checkpoint.json"))
  end
end

class TransferTest < EngineTest
  def test_real_local_transfer_metadata_pause_move_and_seeding
    # OS-assigned ports avoid colliding with a desktop client or another test run.
    require "socket"
    socket = TCPServer.new("127.0.0.1", 0)
    port = socket.addr[1]
    socket.close
    seed = engine("seed", port: port)
    source, torrent = fixture(seed, format: "hybrid")
    seed_id = inspect_torrent(seed, torrent)
    confirm(seed, seed_id)
    eventually { seed.request("list")[0]["progress"] == 1.0 }
    magnet = seed.request("list")[0]["magnet"]
    leech = engine("leech")
    id = inspect_torrent(leech, magnet)
    leech.request("connect_peer", {"torrent" => id, "address" => "127.0.0.1", "port" => port})
    detail = eventually { row = leech.request("details", {"torrent" => id}); row if row["metadata"] }
    assert_equal 0, detail["done"]
    target = File.join(@dir, "download")
    refute File.exist?(File.join(target, "data"))
    confirm(leech, id, target)
    leech.request("pause", {"torrent" => id})
    assert leech.request("list")[0]["paused"]
    leech.request("resume", {"torrent" => id})
    leech.request("connect_peer", {"torrent" => id, "address" => "127.0.0.1", "port" => port})
    eventually(seconds: 40) { leech.request("list")[0]["progress"] == 1.0 }
    assert_equal Digest::SHA256.file(source).hexdigest, Digest::SHA256.file(File.join(target, "data")).hexdigest
    leech.request("recheck", {"torrent" => id})
    eventually { leech.request("list")[0]["progress"] == 1.0 }
    new_target = File.join(@dir, "moved")
    leech.request("move", {"torrent" => id, "destination" => new_target})
    eventually { File.exist?(File.join(new_target, "data")) }
    assert_equal Digest::SHA256.file(source).hexdigest, Digest::SHA256.file(File.join(new_target, "data")).hexdigest
    leech.request("remove", {"torrent" => id, "delete_files" => true, "confirmed" => true})
    eventually { !File.exist?(File.join(new_target, "data")) }
  end
end

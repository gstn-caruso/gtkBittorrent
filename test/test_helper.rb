require "minitest/autorun"
require "tmpdir"
require "fileutils"
require "digest"
require_relative "../lib/gtkbittorrent/engine_client"
require_relative "../lib/gtkbittorrent/store"
require_relative "../lib/gtkbittorrent/transfers"

class EngineTest < Minitest::Test
  def setup
    @dir = Dir.mktmpdir("gtkb-test-")
    @engines = []
  end

  def teardown
    @engines.each { |engine| engine.close rescue nil }
    FileUtils.rm_rf(@dir)
  end

  def engine(name = "state", port: 0)
    state = File.join(@dir, name)
    FileUtils.mkdir_p(state)
    client = GtkBitTorrent::EngineClient.new(state_dir: state, listen: "127.0.0.1:#{port}", discovery: false)
    @engines << client
    client
  end

  def eventually(seconds: 25)
    deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + seconds
    loop do
      result = yield
      return result if result
      raise "Condition did not become true" if Process.clock_gettime(Process::CLOCK_MONOTONIC) > deadline
      sleep 0.1
    end
  end

  def fixture(client, format: "v1", name: "data")
    source = File.join(@dir, name)
    File.binwrite(source, Random.new(3).bytes(512 * 1024)) unless File.exist?(source)
    output = File.join(@dir, "#{name}-#{format}.torrent")
    client.request("create", {"source" => source, "output" => output, "format" => format})
    [source, output]
  end

  def inspect_torrent(client, path)
    client.request("inspect", {"source" => path}).fetch("id")
  end

  def confirm(client, id, destination = @dir)
    client.request("confirm", {"torrent" => id, "destination" => destination})
  end
end

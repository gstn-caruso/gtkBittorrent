module GtkBitTorrent
  VERSION = File.exist?(File.expand_path("../../VERSION", __dir__)) ? File.read(File.expand_path("../../VERSION", __dir__)).strip : "1.0.0-dev"
end

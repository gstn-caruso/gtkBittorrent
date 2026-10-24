require_relative "test_helper"

class StoreTest < Minitest::Test
  def test_atomic_settings_and_fallback
    Dir.mktmpdir do |dir|
      store = GtkBitTorrent::Store.new({"HOME" => dir})
      value = store.load
      value["categories"] = ["Linux"]
      store.save(value)
      value["categories"] << "Documentos"
      store.save(value)
      assert_equal value, store.load
      File.write(File.join(store.config_dir, "preferences.json"), "broken")
      assert_equal ["Linux"], store.load["categories"]
      assert_equal 0o600, File.stat(File.join(store.config_dir, "preferences.json.previous")).mode & 0o777
    end
  end

  def test_remove_requires_confirmation_before_contacting_engine
    transfers = GtkBitTorrent::Transfers.new(nil)
    assert_raises(ArgumentError) { transfers.remove(["1"], delete_files: true) }
  end

  def test_default_destination_uses_localized_xdg_downloads
    Dir.mktmpdir do |dir|
      FileUtils.mkdir_p(File.join(dir, ".config"))
      File.write(File.join(dir, ".config/user-dirs.dirs"), 'XDG_DOWNLOAD_DIR="$HOME/Descargas"' + "\n")
      store = GtkBitTorrent::Store.new({"HOME" => dir})
      assert_equal File.join(dir, "Descargas"), store.load["destination"]
    end
  end
end

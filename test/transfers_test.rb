require_relative "test_helper"

class TransfersTest < Minitest::Test
  class Catalog
    def request(_method)
      [
        {"id" => "1", "name" => "Ubuntu", "progress" => 0.2, "paused" => false, "staged" => false, "category" => "Linux", "error" => ""},
        {"id" => "2", "name" => "Debian", "progress" => 1.0, "paused" => false, "staged" => false, "category" => "Linux", "error" => ""},
        {"id" => "3", "name" => "Documentos", "progress" => 0.0, "paused" => true, "staged" => false, "category" => "", "error" => "disco lleno"},
        {"id" => "4", "name" => "Pendiente", "progress" => 0.0, "paused" => false, "staged" => true, "category" => "", "error" => ""}
      ]
    end
  end

  def test_search_filter_category_and_sort
    transfers = GtkBitTorrent::Transfers.new(Catalog.new)
    assert_equal %w[2 3 1], transfers.list.map { |row| row["id"] }
    assert_equal ["1"], transfers.list(query: "UBU", category: "Linux", filter: "downloading").map { |row| row["id"] }
    assert_equal ["2"], transfers.list(filter: "seeding").map { |row| row["id"] }
    assert_equal ["3"], transfers.list(filter: "paused").map { |row| row["id"] }
    assert_equal ["3"], transfers.list(filter: "error").map { |row| row["id"] }
    assert_equal %w[2 1 3], transfers.list(sort: "progress", descending: true).map { |row| row["id"] }
  end

  def test_filtering_a_snapshot_preserves_the_catalog
    catalog = Catalog.new.request("list")
    transfers = GtkBitTorrent::Transfers.new(nil)

    assert_equal ["1"], transfers.select(catalog, filter: "downloading", query: "ubu").map { |row| row["id"] }
    assert_equal %w[1 2 3 4], catalog.map { |row| row["id"] }
    assert_equal %w[2 1], transfers.select(catalog, category: "Linux").map { |row| row["id"] }
  end
end

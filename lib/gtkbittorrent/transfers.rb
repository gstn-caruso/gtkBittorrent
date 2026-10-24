module GtkBitTorrent
  class Transfers
    def initialize(engine)
      @engine = engine
    end

    def list(query: "", filter: "all", category: nil, sort: "name", descending: false)
      rows = @engine.request("list")
      rows = rows.reject { |row| row["staged"] }
      rows = rows.select { |row| row["name"].downcase.include?(query.downcase) }
      rows = rows.select { |row| row["category"] == category } if category
      rows = rows.select do |row|
        case filter
        when "downloading" then !row["paused"] && row["progress"] < 1
        when "seeding" then !row["paused"] && row["progress"] >= 1
        when "paused" then row["paused"]
        when "error" then !row["error"].to_s.empty?
        else true
        end
      end
      rows = rows.sort_by { |row| row.fetch(sort) }
      descending ? rows.reverse : rows
    end

    def remove(ids, delete_files: false, confirmed: false)
      raise ArgumentError, "Confirme explícitamente el borrado de archivos" if delete_files && !confirmed
      ids.each { |id| @engine.request("remove", {"torrent" => id, "delete_files" => delete_files, "confirmed" => confirmed}) }
    end
  end
end

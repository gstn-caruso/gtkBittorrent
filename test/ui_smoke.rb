require "tmpdir"
require "fileutils"
require "open3"
require "timeout"
root = File.expand_path("..", __dir__)
Dir.mktmpdir("gtkb-ui-") do |dir|
  ENV["XDG_STATE_HOME"] = File.join(dir, "state")
  ENV["XDG_CONFIG_HOME"] = File.join(dir, "config")
  require_relative "../lib/gtkbittorrent/ui"
  {0 => "0 B", 512 => "512 B", 1024 => "1.0 KiB", 1536 => "1.5 KiB",
   10 * 1024**2 => "10 MiB", 2 * 1024**3 => "2.0 GiB", 1024**5 => "1024 TiB"}.each do |value, expected|
    actual = GtkBitTorrent::Format.bytes(value)
    raise "Expected #{expected}, got #{actual}" unless actual == expected
  end
  app = GtkBitTorrent::Application.new
  failure = nil
  phase = 0
  first_id = nil
  app.signal_connect("activate") do
    next unless phase == 0
    GLib::Timeout.add(400) do
      begin
        case phase
        when 0
          raise "No main window" unless app.window.visible?
          raise "Actions enabled without a selection" if app.window.instance_variable_get(:@selection_buttons).any?(&:sensitive?)
          raise "Summary visible without a selection" if app.window.instance_variable_get(:@summary).visible?
          raise "Selection actions visible without a selection" if app.window.instance_variable_get(:@selection_controls).visible?
          raise "Search should start closed" if app.window.instance_variable_get(:@search_bar).search_mode_enabled?
          source = File.join(dir, "sample.txt")
          torrent = File.join(dir, "sample.torrent")
          File.write(source, "GtkBitTorrent UI test\n")
          app.engine.request("create", {"source" => source, "output" => torrent})
          row = app.engine.request("inspect", {"source" => torrent})
          app.window.confirm_dialog(row)
          GC.start
          phase = 1
        when 1
          confirmation = app.window.instance_variable_get(:@dialogs)&.find { |dialog| dialog.title == "Añadir transferencia" }
          widgets = []
          visit = ->(widget) {
            widgets << widget
            child = widget.first_child
            while child
              visit.call(child)
              child = child.next_sibling
            end
          }
          visit.call(confirmation) if confirmation
          accept = widgets.find { |widget| widget.is_a?(Gtk::Button) && widget.label == "Iniciar descarga" }
          if accept&.sensitive?
            fields = widgets.select { |widget| widget.is_a?(Adwaita::EntryRow) }
            fields[0].text = dir
            fields[1].text = "Prueba"
            accept.signal_emit("clicked")
            phase = 2
          end
        when 2
          rows = app.window.instance_variable_get(:@rows)
          if rows.any?
            first_id = rows[0]["id"]
            raise "Transfer selected without user input" unless app.window.selected_ids.empty?
            raise "Wrong singular transfer count" unless app.window.instance_variable_get(:@status).text == "1 transferencia"
            app.window.instance_variable_get(:@selection).select_item(0, true)
            raise "Missing selection summary" unless app.window.instance_variable_get(:@summary).visible?
            raise "Pause unavailable for active transfer" unless app.window.instance_variable_get(:@pause_button).visible?
            raise "Resume offered for active transfer" if app.window.instance_variable_get(:@resume_button).visible?
            app.window.instance_variable_get(:@pause_button).signal_emit("clicked")
            app.window.lookup_action("details").activate(nil)
            raise "Details shortcut did not open pane" unless app.window.instance_variable_get(:@details_split).show_sidebar?
            raise "Details toggle is out of sync" unless app.window.instance_variable_get(:@details_toggle).active?
            app.window.lookup_action("details").activate(nil)
            source = File.join(dir, "second.txt")
            torrent = File.join(dir, "second.torrent")
            File.write(source, "Another local UI fixture\n")
            app.engine.request("create", {"source" => source, "output" => torrent})
            row = app.engine.request("inspect", {"source" => torrent})
            app.engine.request("confirm", {"torrent" => row["id"], "destination" => dir})
            app.window.refresh
            phase = 3
          end
        when 3
          rows = app.window.instance_variable_get(:@rows)
          if rows.size == 2 && rows.find { |row| row["id"] == first_id }["paused"] && !app.window.instance_variable_get(:@busy)
            raise "Pause offered for paused transfer" if app.window.instance_variable_get(:@pause_button).visible?
            raise "Resume unavailable for paused transfer" unless app.window.instance_variable_get(:@resume_button).visible?
            selection = app.window.instance_variable_get(:@selection)
            selection.select_all
            raise "Pause unavailable for mixed selection" unless app.window.instance_variable_get(:@pause_button).visible?
            raise "Resume unavailable for mixed selection" unless app.window.instance_variable_get(:@resume_button).visible?
            selection.select_item(rows.index { |row| row["id"] == first_id }, true)
            app.window.instance_variable_get(:@resume_button).signal_emit("clicked")
            app.window.instance_variable_get(:@table).sort_by_column(app.window.instance_variable_get(:@columns)["name"], :descending)
            phase = 4
          end
        when 4
          unless app.window.instance_variable_get(:@busy)
            rows = app.window.instance_variable_get(:@rows)
            raise "Sort did not reverse rows" unless rows.last["id"] == first_id
            raise "Selection changed after sorting" unless app.window.selected_ids == [first_id]
            raise "Resume did not restart transfer" if rows.last["paused"]
            raise "Resume remained visible for active transfer" if app.window.instance_variable_get(:@resume_button).visible?
            selection = app.window.instance_variable_get(:@selection)
            selection.select_all
            raise "Missing multiple selection summary" unless app.window.instance_variable_get(:@summary_name).text == "2 transferencias seleccionadas"
            raise "Properties enabled for multiple transfers" if app.window.instance_variable_get(:@properties).sensitive?
            app.window.refresh
            phase = 5
          end
        when 5
          unless app.window.instance_variable_get(:@busy)
            raise "Multiple selection lost during refresh" unless app.window.selected_ids.size == 2
            app.window.instance_variable_get(:@selection).unselect_all
            raise "Actions enabled after deselecting" if app.window.instance_variable_get(:@selection_buttons).any?(&:sensitive?)
            raise "Selection actions remained visible" if app.window.instance_variable_get(:@selection_controls).visible?
            app.window.refresh
            phase = 6
          end
        when 6
          unless app.window.instance_variable_get(:@busy)
            raise "Refresh restored a cleared selection" unless app.window.selected_ids.empty?
            app.window.lookup_action("search").activate(nil)
            raise "Search shortcut did not open search" unless app.window.instance_variable_get(:@search_bar).search_mode_enabled?
            app.window.instance_variable_get(:@search).text = "no matching transfer"
            app.window.refresh
            phase = 7
          end
        when 7
          if app.window.instance_variable_get(:@rows).empty? && !app.window.instance_variable_get(:@busy)
            raise "Wrong filtered empty state" unless app.window.instance_variable_get(:@empty).title == "No hay coincidencias"
            raise "Global count changed with search" unless app.window.instance_variable_get(:@sidebar_counts).first.text == "2"
            raise "Summary visible for filtered-out selection" if app.window.instance_variable_get(:@summary).visible?
            app.window.instance_variable_get(:@clear_filters).signal_emit("clicked")
            phase = 8
          end
        when 8
          if app.window.instance_variable_get(:@rows).size == 2 && !app.window.instance_variable_get(:@busy)
            sidebar = app.window.instance_variable_get(:@sidebar)
            sidebar.select_row(sidebar.get_row_at_index(5))
            phase = 9
          end
        when 9
          if app.window.instance_variable_get(:@rows).size == 1 && !app.window.instance_variable_get(:@busy)
            raise "Category filter shows wrong transfer" unless app.window.instance_variable_get(:@rows).map { |row| row["id"] } == [first_id]
            app.window.instance_variable_get(:@selection).select_item(0, true)
            app.window.rebuild_sidebar
            raise "Rebuilding sidebar lost the active category" unless app.window.instance_variable_get(:@category) == "Prueba"
            raise "Rebuilding sidebar selected the wrong row" unless app.window.instance_variable_get(:@sidebar).selected_row.index == 5
            app.window.clear_filters
            app.window.set_default_size(360, 760)
            phase = 10
          end
        when 10
          if app.window.instance_variable_get(:@rows).size == 2 && !app.window.instance_variable_get(:@busy)
            split = app.window.instance_variable_get(:@split)
            raise "Navigation did not adapt to narrow width" unless split.collapsed?
            raise "Details did not adapt to narrow width" unless app.window.instance_variable_get(:@details_split).collapsed?
            raise "Main menu unavailable at narrow width" unless app.window.instance_variable_get(:@compact_menu).visible?
            split.show_content = false
            sidebar = app.window.instance_variable_get(:@sidebar)
            sidebar.signal_emit("row-activated", sidebar.selected_row)
            raise "Activating current filter did not restore content" unless split.show_content?
            app.window.show_details(first_id)
            %w[preferences categories create].each { |name| app.window.lookup_action(name).activate(nil) }
            phase = 11
          end
        when 11
          dialogs = app.window.instance_variable_get(:@dialogs)
          if dialogs.any?
            dialogs.dup.reverse_each(&:close)
          else
            app.window.close
            raise "Window should hide" if app.window.visible?
            phase = 12
            Thread.new do
              output, status = Open3.capture2e(RbConfig.ruby, File.join(root, "bin/gtkbittorrent"), "--version")
              raise "Version flag failed: #{output}" unless status.success?
              # A second launch must forward activation and exit without another engine.
              _out, status = Timeout.timeout(10) { Open3.capture2e(RbConfig.ruby, File.join(root, "bin/gtkbittorrent")) }
              raise "Second instance failed" unless status.success?
              GLib::Idle.add { phase = 13; false }
            rescue StandardError => error
              GLib::Idle.add { failure = error; app.quit; false }
            end
          end
        when 13
          raise "Second launch did not restore window" unless app.window.visible?
          app.quit_safely
          phase = 14
        end
      rescue StandardError => error
        failure = error
        app.quit
      end
      phase < 14 && failure.nil?
    end
  end
  GLib::Timeout.add(25_000) { failure = "UI timeout in phase #{phase}"; app.quit; false }
  result = app.run(["gtkb-ui-test"])
  raise failure if failure
  raise "Application exit #{result}" unless result.zero?
  raise "UI did not complete all checks" unless phase == 14
  raise "Missing final checkpoint" unless File.file?(File.join(dir, "state/gtkbittorrent/checkpoint.json"))
end
puts "UI, selection, filters, background, second instance and clean exit: OK"

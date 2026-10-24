require "tmpdir"
require "fileutils"
require "open3"
require "timeout"
root = File.expand_path("..", __dir__)
Dir.mktmpdir("gtkb-ui-") do |dir|
  ENV["XDG_STATE_HOME"] = File.join(dir, "state")
  ENV["XDG_CONFIG_HOME"] = File.join(dir, "config")
  require_relative "../lib/gtkbittorrent/ui"
  app = GtkBitTorrent::Application.new
  failure = nil
  phase = 0
  app.signal_connect("activate") do
    next unless phase == 0
    GLib::Timeout.add(400) do
      begin
        case phase
        when 0
          raise "No main window" unless app.window.visible?
          source = File.join(dir, "sample.txt")
          torrent = File.join(dir, "sample.torrent")
          File.write(source, "GtkBitTorrent UI test\n")
          app.engine.request("create", {"source" => source, "output" => torrent})
          row = app.engine.request("inspect", {"source" => torrent})
          app.window.confirm_dialog(row)
          GC.start
          phase = 1
        when 1
          confirmation = Gtk::Window.list_toplevels.find { |window| window.title == "Añadir transferencia" }
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
            fields = widgets.select { |widget| widget.is_a?(Gtk::Entry) }
            fields[0].text = dir
            fields[1].text = "Prueba"
            accept.signal_emit("clicked")
            phase = 2
          end
        when 2
          rows = app.window.instance_variable_get(:@rows)
          if rows.any?
            id = rows[0]["id"]
            app.window.show_details(id)
            app.window.preferences
            app.window.new_category
            app.window.create_torrent
            app.window.close
            raise "Window should hide" if app.window.visible?
            phase = 3
          Thread.new do
            output, status = Open3.capture2e(RbConfig.ruby, File.join(root, "bin/gtkbittorrent"), "--version")
            raise "Version flag failed: #{output}" unless status.success?
            # A second launch must forward activation and exit without another engine.
            _out, status = Timeout.timeout(10) { Open3.capture2e(RbConfig.ruby, File.join(root, "bin/gtkbittorrent")) }
            raise "Second instance failed" unless status.success?
            GLib::Idle.add { phase = 4; false }
          rescue StandardError => error
            GLib::Idle.add { failure = error; app.quit; false }
          end
          end
        when 4
          raise "Second launch did not restore window" unless app.window.visible?
          app.quit_safely
          phase = 5
        end
      rescue StandardError => error
        failure = error
        app.quit
      end
      phase < 5 && failure.nil?
    end
  end
  GLib::Timeout.add(15_000) { failure = "UI timeout"; app.quit; false }
  result = app.run(["gtkb-ui-test"])
  raise failure if failure
  raise "Application exit #{result}" unless result.zero?
  raise "UI did not complete all checks" unless phase == 5
  raise "Missing final checkpoint" unless File.file?(File.join(dir, "state/gtkbittorrent/checkpoint.json"))
end
puts "UI, background, second instance and clean exit: OK"

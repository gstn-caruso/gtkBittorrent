gem "gtk4", "4.3.9"
gem "adwaita", "4.3.9"
require "gtk4"
require "adwaita"
require "uri"
require_relative "store"
require_relative "engine_client"
require_relative "transfers"

module GtkBitTorrent
  module Format
    def self.bytes(value)
      value = value.to_f
      unit = %w[B KiB MiB GiB TiB].find { |candidate| break candidate if value < 1024; value /= 1024 } || "TiB"
      "#{format(value < 10 ? '%.1f' : '%.0f', value)} #{unit}"
    end

    def self.state(row)
      return row["error"] unless row["error"].to_s.empty?
      return "En pausa" if row["paused"]
      return "En cola" if row["queued"]
      return "Recuperando metadatos" unless row["metadata"]
      return "Verificando" if [1, 7].include?(row["state"])
      row["progress"] >= 1 ? "Compartiendo" : "Descargando"
    end
  end

  class Application < Adwaita::Application
    attr_reader :engine, :settings, :store, :window

    def initialize
      super("org.gtkbittorrent.GtkBitTorrent", :handles_command_line)
      @jobs = Queue.new
      signal_connect("startup") { start }
      signal_connect("activate") { activate_window }
      signal_connect("command-line") do |_app, command|
        args = command.arguments.drop(1)
        if args.include?("--quit")
          quit_safely
        else
          activate
          args.reject { |arg| arg.start_with?("--") }.each do |source|
            source = command.create_file_for_arg(source).path unless source.start_with?("magnet:?")
            @window.add_source(source)
          end
          GLib::Timeout.add(1200) { quit_safely; false } if args.include?("--smoke-test")
        end
        command.exit_status = 0
        command.done
        0
      end
      signal_connect("shutdown") do
        @jobs.push(nil)
        @worker&.join(2)
        @engine&.close
      end
    end

    def start
      @store = Store.new
      @settings = @store.load
      @engine = EngineClient.new(state_dir: store.state_dir)
      @engine.request("limits", settings.fetch("limits"))
      hold
      @worker = Thread.new do
        while (job = @jobs.pop)
          perform_job(*job)
        end
      end
    rescue StandardError => error
      warn error.message
      raise
    end

    def async(success = nil, &work)
      @jobs.push([work, success])
    end

    def perform_job(work, success)
      result = work.call
      GLib::Idle.add { success&.call(result); false }
    rescue StandardError => error
      message = error.message
      GLib::Idle.add { @quitting = false; @window&.error(message); false }
    end

    def save_settings
      store.save(settings)
    end

    def activate_window
      @window ||= MainWindow.new(self)
      @window.present
    end

    def quit_safely
      return if @quitting
      @quitting = true
      async(->(_) { release; quit }) { save_settings; engine.request("checkpoint") }
    end
  end

  class MainWindow < Adwaita::ApplicationWindow
    def initialize(app)
      super(app)
      @app = app
      @filter = "all"
      @rows = []
      @busy = false
      self.title = "GtkBitTorrent"
      self.default_width = 1180
      self.default_height = 760
      signal_connect("close-request") { self.visible = false; true }
      build
      GLib::Timeout.add(1000) { refresh; true }
      refresh
    end

    def button(label, tooltip = label, &block)
      widget = Gtk::Button.new(label: label)
      widget.tooltip_text = tooltip
      widget.signal_connect("clicked", &block)
      widget
    end

    def box(spacing = 8)
      Gtk::Box.new(:vertical, spacing)
    end

    def padded(widget, amount = 12)
      widget.margin_top = widget.margin_bottom = widget.margin_start = widget.margin_end = amount
      widget
    end

    def build
      toolbar = Adwaita::ToolbarView.new
      header = Adwaita::HeaderBar.new
      header.pack_start(button("Abrir torrent", "Abrir un archivo .torrent") { choose_file { |path| add_source(path) } })
      header.pack_start(button("Añadir magnet") { prompt("Añadir magnet", "Enlace magnet", "magnet:?") { |source| add_source(source) } })
      menu = Gio::Menu.new
      {"create" => ["Crear torrent", -> { create_torrent }], "preferences" => ["Preferencias", -> { preferences }],
       "categories" => ["Nueva categoría", -> { new_category }], "restart" => ["Reiniciar motor", -> { restart_engine }],
       "quit" => ["Salir", -> { @app.quit_safely }]}.each do |name, (label, action)|
        simple = Gio::SimpleAction.new(name)
        simple.signal_connect("activate", &action)
        add_action(simple)
        menu.append(label, "win.#{name}")
      end
      menu_button = Gtk::MenuButton.new
      menu_button.icon_name = "open-menu-symbolic"
      menu_button.menu_model = menu
      menu_button.tooltip_text = "Menú de la aplicación"
      header.pack_end(menu_button)
      toolbar.add_top_bar(header)
      @split = Adwaita::OverlaySplitView.new
      @split.min_sidebar_width = 180
      @split.max_sidebar_width = 220
      @sidebar = Gtk::ListBox.new
      @sidebar.add_css_class("navigation-sidebar")
      @sidebar.signal_connect("row-selected") do |_list, row|
        if row
          value = @navigation[row.index]
          @filter, @category = value
          refresh
        end
      end
      rebuild_sidebar
      sidebar_scroll = Gtk::ScrolledWindow.new
      sidebar_scroll.child = @sidebar
      @split.sidebar = sidebar_scroll
      toggle = button("Vistas") { @split.show_sidebar = !@split.show_sidebar? }
      header.pack_start(toggle)
      breakpoints = Adwaita::Breakpoint.new(Adwaita::BreakpointCondition.parse("max-width: 760sp"))
      breakpoints.add_setter(@split, "collapsed", true)
      add_breakpoint(breakpoints)
      main = box(0)
      search_bar = Gtk::Box.new(:horizontal, 8)
      @search = Gtk::SearchEntry.new
      @search.hexpand = true
      @search.placeholder_text = "Buscar transferencias"
      @search.signal_connect("search-changed") { refresh }
      search_bar.append(@search)
      @sort = Gtk::DropDown.new(%w[Nombre Progreso Descarga Subida Tamaño Cola])
      @sort.tooltip_text = "Ordenar transferencias"
      @sort.signal_connect("notify::selected") { refresh }
      search_bar.append(@sort)
      @descending = Gtk::CheckButton.new("Descendente")
      @descending.signal_connect("toggled") { refresh }
      search_bar.append(@descending)
      main.append(padded(search_bar))
      @model = Gtk::StringList.new([])
      @selection = Gtk::MultiSelection.new(@model)
      @table = Gtk::ColumnView.new(@selection)
      @table.show_row_separators = true
      columns = {"Nombre" => ->(r) { r["name"] }, "Estado" => ->(r) { Format.state(r) },
        "Progreso" => ->(r) { "#{(r['progress'] * 100).round(1)} %" }, "Tamaño" => ->(r) { Format.bytes(r["size"]) },
        "Descarga" => ->(r) { "#{Format.bytes(r['download_rate'])}/s" }, "Subida" => ->(r) { "#{Format.bytes(r['upload_rate'])}/s" },
        "ETA" => ->(r) { r["eta"] < 0 ? "—" : "#{r['eta'] / 60} min" }, "Ratio" => ->(r) { format("%.2f", r["ratio"]) }}
      columns.each do |title, formatter|
        factory = Gtk::SignalListItemFactory.new
        factory.signal_connect("setup") { |_factory, item| item.child = Gtk::Label.new(""); item.child.xalign = 0; item.child.margin_start = item.child.margin_end = 10 }
        factory.signal_connect("bind") do |_factory, item|
          item.child.text = formatter.call(JSON.parse(item.item.string))
          item.child.tooltip_text = item.child.text
        end
        column = Gtk::ColumnViewColumn.new(title, factory)
        column.resizable = true
        column.expand = title == "Nombre"
        @table.append_column(column)
      end
      @table.signal_connect("activate") { |_view, position| show_details(@rows[position]["id"]) }
      scroll = Gtk::ScrolledWindow.new
      scroll.vexpand = true
      scroll.child = @table
      @content_stack = Gtk::Stack.new
      @content_stack.add_named(scroll, "table")
      empty = Adwaita::StatusPage.new
      empty.icon_name = "folder-download-symbolic"
      empty.title = "Tus transferencias, en un lugar"
      empty.description = "Abre un torrent o añade un magnet para empezar."
      @content_stack.add_named(empty, "empty")
      main.append(@content_stack)
      actions = Gtk::Box.new(:horizontal, 6)
      {"Pausar" => "pause", "Reanudar" => "resume", "Verificar" => "recheck"}.each { |label, method| actions.append(button(label) { selected_action(method) }) }
      actions.append(button("Detalles") { selected_ids.first.then { |id| show_details(id) if id } })
      actions.append(button("Ubicación") { choose_file(folder: true) { |path| selected_action("move", {"destination" => path}) } })
      actions.append(button("Eliminar") { remove_selected })
      main.append(padded(actions))
      @status = Gtk::Label.new("Preparando motor…")
      @status.xalign = 0
      @status.add_css_class("dim-label")
      main.append(padded(@status))
      @split.content = main
      @toasts = Adwaita::ToastOverlay.new
      @toasts.child = @split
      toolbar.content = @toasts
      self.content = toolbar
    end

    def rebuild_sidebar
      while (child = @sidebar.first_child)
        @sidebar.remove(child)
      end
      @navigation = [["all", nil], ["downloading", nil], ["seeding", nil], ["paused", nil], ["error", nil]]
      names = ["Todas las transferencias", "Descargando", "Compartiendo", "En pausa", "Con errores"]
      @app.settings["categories"].each { |category| @navigation << ["all", category]; names << category }
      names.each { |name| @sidebar.append(padded(Gtk::Label.new(name).tap { |label| label.xalign = 0 })) }
      @sidebar.select_row(@sidebar.get_row_at_index(0))
    end

    def selected_ids
      @rows.each_index.select { |i| @selection.selected?(i) }.map { |i| @rows[i]["id"] }
    end

    def refresh
      return if @busy || !@search
      @busy = true
      query, filter, category = @search.text, @filter, @category
      sort = %w[name progress download_rate upload_rate size queue][@sort.selected]
      descending = @descending.active?
      @app.async(->(rows) {
        ids = selected_ids
        @rows = rows
        @model.splice(0, @model.n_items, rows.map { |row| JSON.generate(row) })
        rows.each_with_index { |row, i| @selection.select_item(i, false) if ids.include?(row["id"]) }
        @content_stack.visible_child_name = rows.empty? ? "empty" : "table"
        @status.text = "#{rows.size} transferencias   ↓ #{Format.bytes(rows.sum { |r| r['download_rate'] })}/s   ↑ #{Format.bytes(rows.sum { |r| r['upload_rate'] })}/s"
        @busy = false
      }) do
        begin
          rows = Transfers.new(@app.engine).list(query: query, filter: filter, category: category, sort: sort, descending: descending)
          events = @app.engine.events
          events.select { |event| event["event"] == "error" }.each do |event|
            GLib::Idle.add { error(event["data"].to_s); false }
          end
          rows
        rescue StandardError
          GLib::Idle.add { @busy = false; false }
          raise
        end
      end
    end

    def selected_action(method, params = {})
      ids = selected_ids
      @app.async(->(_) { refresh }) { ids.each { |id| @app.engine.request(method, params.merge("torrent" => id)) } }
    end

    def error(message)
      if @last_error != message
        @toasts.add_toast(Adwaita::Toast.new(message))
        warn message
      end
      @last_error = message
      @status.text = message
    end

    def dialog(title, width: 620)
      window = Adwaita::Window.new
      @dialogs ||= []
      @dialogs << window
      window.signal_connect("close-request") { @dialogs.delete(window); false }
      window.transient_for = self
      window.modal = true
      window.title = title
      window.default_width = width
      window.default_height = 500
      toolbar = Adwaita::ToolbarView.new
      toolbar.add_top_bar(Adwaita::HeaderBar.new)
      body = padded(box)
      scroll = Gtk::ScrolledWindow.new
      scroll.child = body
      scroll.vexpand = true
      toolbar.content = scroll
      window.content = toolbar
      yield window, body
      window.present
      window
    end

    def entry(body, label, value = "")
      caption = Gtk::Label.new(label)
      caption.xalign = 0
      body.append(caption)
      Gtk::Entry.new.tap do |widget|
        widget.text = value.to_s
        widget.tooltip_text = label
        caption.mnemonic_widget = widget
        body.append(widget)
      end
    end

    def prompt(title, label, initial = "", &action)
      dialog(title) do |win, body|
        field = entry(body, label, initial)
        body.append(button("Aceptar") { action.call(field.text); win.close })
      end
    end

    def choose_file(folder: false, save: false, &action)
      chooser = Gtk::FileChooserNative.new(folder ? "Elegir carpeta" : "Elegir archivo", self, folder ? :select_folder : save ? :save : :open, "Elegir", "Cancelar")
      chooser.signal_connect("response") do |_widget, response|
        action.call(chooser.file.path) if response == Gtk::ResponseType::ACCEPT && chooser.file
        chooser.destroy
      end
      chooser.show
    end

    def add_source(source)
      @app.async(->(row) { confirm_dialog(row) }) { @app.engine.request("inspect", {"source" => source}) }
    end

    def confirm_dialog(row)
      id = row["id"]
      committed = false
      loading = false
      file_controls = nil
      dialog("Añadir transferencia") do |win, body|
        status = Gtk::Label.new("Recuperando metadatos…")
        body.append(status)
        target = entry(body, "Carpeta de destino", @app.settings["destination"])
        body.append(button("Elegir carpeta") { choose_file(folder: true) { |path| target.text = path } })
        category = entry(body, "Categoría (opcional)")
        files_box = box
        body.append(files_box)
        accept = button("Iniciar descarga") do
          accept.sensitive = false
          values = file_controls.map { |control| control.selected }
          params = {"torrent" => id, "destination" => target.text, "category" => category.text, "priorities" => values}
          @app.async(->(_) {
            committed = true
            @app.settings["destination"] = target.text
            @app.settings["categories"] |= [category.text] unless category.text.empty?
            @app.save_settings
            rebuild_sidebar
            win.close
            refresh
          }) do
            begin
              @app.engine.request("confirm", params)
            rescue StandardError
              GLib::Idle.add { accept.sensitive = true; false }
              raise
            end
          end
        end
        accept.add_css_class("suggested-action")
        accept.sensitive = false
        body.append(accept)
        timer = GLib::Timeout.add(500) do
          unless loading
            loading = true
            @app.async(->(detail) {
              loading = false
              if detail["metadata"] && !file_controls
                status.text = "#{detail['name']} — #{Format.bytes(detail['size'])}"
                file_controls = priority_controls(files_box, detail["files"])
                accept.sensitive = true
              end
            }) { @app.engine.request("details", {"torrent" => id}) }
          end
          !file_controls
        end
        win.signal_connect("close-request") do
          GLib::Source.remove(timer) unless file_controls
          @app.async { @app.engine.request("remove", {"torrent" => id}) } unless committed
          false
        end
      end
    end

    def priority_controls(body, files)
      files.map do |file|
        row = Gtk::Box.new(:horizontal, 8)
        label = Gtk::Label.new("#{file['path']} (#{Format.bytes(file['size'])})")
        label.xalign = 0; label.hexpand = true; label.wrap = true
        row.append(label)
        control = Gtk::DropDown.new(["Omitir", "1", "2", "3", "Normal", "5", "6", "Alta"])
        control.selected = file["padding"] ? 0 : file["priority"]
        control.sensitive = !file["padding"]
        row.append(control)
        body.append(row)
        control
      end
    end

    def show_details(id)
      @app.async(->(detail) {
        dialog(detail["name"], width: 780) do |win, body|
          stack = Gtk::Stack.new
          switcher = Gtk::StackSwitcher.new
          switcher.stack = stack
          body.append(switcher)
          body.append(stack)
          files = box
          controls = priority_controls(files, detail["files"])
          files.append(button("Guardar prioridades") {
            @app.async { @app.engine.request("priorities", {"torrent" => id, "priorities" => controls.map(&:selected)}) }
          })
          stack.add_titled(files, "files", "Archivos")
          trackers = box
          urls = entry(trackers, "Trackers separados por espacios", detail["trackers"].map { |tracker| tracker["url"] }.join(" "))
          detail["trackers"].each do |tracker|
            unless tracker["error"].to_s.empty?
              label = Gtk::Label.new("#{tracker['url']}: #{tracker['error']}")
              label.wrap = true
              trackers.append(label)
            end
          end
          trackers.append(button("Guardar trackers") do
            values = urls.text.split
            @app.async { @app.engine.request("trackers", {"torrent" => id, "trackers" => values}) }
          end)
          stack.add_titled(trackers, "trackers", "Trackers")
          peers = box
          detail["peers_detail"].each { |peer| peers.append(Gtk::Label.new("#{peer['address']}:#{peer['port']}   #{peer['client']}   #{(peer['progress'] * 100).round}%   ↓ #{Format.bytes(peer['download_rate'])}/s")) }
          peers.append(Gtk::Label.new("No hay peers conectados")) if detail["peers_detail"].empty?
          peers.append(button("Actualizar") { win.close; show_details(id) })
          stack.add_titled(peers, "peers", "Peers")
          options = box
          category = entry(options, "Categoría", detail["category"])
          queue = entry(options, "Posición en cola (desde 0)", [detail["queue"], 0].max)
          down = entry(options, "Límite de descarga (B/s, 0 sin límite)", detail["download_limit"])
          up = entry(options, "Límite de subida (B/s, 0 sin límite)", detail["upload_limit"])
          entry(options, "Magnet", detail["magnet"])
          options.append(Gtk::Label.new("Destino: #{detail['destination']}"))
          options.append(button("Guardar opciones") do
            values = {"torrent" => id, "download" => Integer(down.text), "upload" => Integer(up.text), "position" => Integer(queue.text)} rescue nil
            name = category.text
            if values
              @app.async(->(_) {
                @app.settings["categories"] |= [name] unless name.empty?
                @app.save_settings
                rebuild_sidebar
                win.close
                refresh
              }) do
                @app.engine.request("limits", values)
                @app.engine.request("category", {"torrent" => id, "category" => name})
                @app.engine.request("queue", {"torrent" => id, "position" => values["position"]})
              end
            else error("Los límites deben ser números enteros")
            end
          end)
          stack.add_titled(options, "options", "Opciones")
        end
      }) { @app.engine.request("details", {"torrent" => id}) }
    end

    def remove_selected
      ids = selected_ids
      return if ids.empty?
      dialog("Eliminar #{ids.size} transferencias") do |win, body|
        body.append(Gtk::Label.new("Los archivos se conservarán salvo que marques la siguiente opción."))
        erase = Gtk::CheckButton.new("Borrar también los archivos descargados")
        body.append(erase)
        body.append(button("Confirmar eliminación") do
          delete_files = erase.active?
          @app.async(->(_) { win.close; refresh }) { Transfers.new(@app.engine).remove(ids, delete_files: delete_files, confirmed: delete_files) }
        end)
      end
    end

    def new_category
      prompt("Nueva categoría", "Nombre") do |name|
        next if name.strip.empty?
        @app.settings["categories"] |= [name.strip]
        @app.save_settings
        rebuild_sidebar
      end
    end

    def preferences
      dialog("Preferencias") do |win, body|
        fields = {"download" => "Descarga global (B/s, 0 sin límite)", "upload" => "Subida global (B/s, 0 sin límite)",
          "active_downloads" => "Descargas simultáneas", "active_seeds" => "Torrents compartidos simultáneos"}.transform_values.with_index do |label, index|
          key = %w[download upload active_downloads active_seeds][index]
          entry(body, label, @app.settings["limits"][key])
        end
        body.append(Gtk::Label.new("Al cerrar la ventana, las transferencias continúan. Usa Salir para detener el cliente."))
        body.append(Gtk::Label.new("GtkBitTorrent #{VERSION}"))
        body.append(button("Guardar") do
          begin
            values = fields.transform_values { |field| Integer(field.text) }
            raise ArgumentError if values.values.any?(&:negative?)
            @app.async(->(_) { @app.settings["limits"] = values; @app.save_settings; win.close }) { @app.engine.request("limits", values) }
          rescue ArgumentError
            error("Usa números enteros mayores o iguales a cero")
          end
        end)
      end
    end

    def create_torrent
      dialog("Crear torrent") do |win, body|
        source = entry(body, "Archivo o carpeta de origen")
        body.append(button("Elegir archivo") { choose_file { |path| source.text = path } })
        body.append(button("Elegir carpeta") { choose_file(folder: true) { |path| source.text = path } })
        output = entry(body, "Nuevo archivo .torrent (ruta completa)")
        format = Gtk::DropDown.new(["v1", "v2", "Híbrido"])
        body.append(format)
        trackers = entry(body, "Trackers separados por espacios (opcional)")
        private_torrent = Gtk::CheckButton.new("Torrent privado")
        body.append(private_torrent)
        create = button("Crear") do
          params = {"source" => source.text, "output" => output.text, "format" => %w[v1 v2 hybrid][format.selected], "trackers" => trackers.text.split, "private" => private_torrent.active?}
          @app.async(->(_) { win.close; @toasts.add_toast(Adwaita::Toast.new("Torrent creado")) }) { @app.engine.request("create", params, timeout: 3600) }
        end
        body.append(create)
      end
    end

    def restart_engine
      @app.async(->(_) { @busy = false; refresh }) do
        @app.engine.close rescue nil
        @app.instance_variable_set(:@engine, EngineClient.new(state_dir: @app.store.state_dir))
      end
    end
  end
end

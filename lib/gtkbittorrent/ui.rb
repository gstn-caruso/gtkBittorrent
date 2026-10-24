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
      units = %w[B KiB MiB GiB TiB]
      unit = 0
      while value >= 1024 && unit < units.size - 1
        value /= 1024
        unit += 1
      end
      "#{format(unit.zero? || value >= 10 ? '%.0f' : '%.1f', value)} #{units[unit]}"
    end

    def self.state(row)
      return row["error"] unless row["error"].to_s.empty?
      return "En pausa" if row["paused"]
      return "En cola" if row["queued"]
      return "Recuperando metadatos" unless row["metadata"]
      return "Verificando" if [1, 7].include?(row["state"])
      row["progress"] >= 1 ? "Compartiendo" : "Descargando"
    end

    def self.transfers(count)
      "#{count} #{count == 1 ? 'transferencia' : 'transferencias'}"
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
      self.width_request = 360
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

    def icon_button(icon, label, &action)
      widget = button(label, &action)
      widget.icon_name = icon
      widget
    end

    def selection_button(icon, label, &action)
      widget = icon_button(icon, label, &action)
      widget.sensitive = false
      @selection_buttons << widget
      widget
    end

    def build
      @selection_buttons = []
      @selection_actions = []
      @sort_key = "name"
      @sort_descending = false
      build_actions
      @split = Adwaita::NavigationSplitView.new
      @split.min_sidebar_width = 200
      @split.max_sidebar_width = 240
      @split.sidebar = Adwaita::NavigationPage.new(build_sidebar, "GtkBitTorrent")
      @content_page = Adwaita::NavigationPage.new(build_transfers, "Transferencias")
      @split.content = @content_page
      @split.show_content = true
      details = Adwaita::Breakpoint.new(Adwaita::BreakpointCondition.parse("max-width: 1100sp"))
      details.add_setter(@details_split, "collapsed", true)
      add_breakpoint(details)
      narrow = Adwaita::Breakpoint.new(Adwaita::BreakpointCondition.parse("max-width: 760sp"))
      narrow.add_setter(@split, "collapsed", true)
      narrow.add_setter(@compact_menu, "visible", true)
      narrow.add_setter(@details_split, "collapsed", true)
      narrow.add_setter(@header, "decoration-layout", ":close")
      narrow.add_setter(@details_toggle, "visible", false)
      narrow.add_setter(@selection_menu_button, "visible", false)
      narrow.add_setter(@table, "margin-start", 8)
      narrow.add_setter(@table, "margin-end", 8)
      narrow.add_setter(@columns["name"], "fixed-width", 170)
      narrow.add_setter(@columns["progress"], "fixed-width", 140)
      %w[size state download_rate upload_rate].each { |key| narrow.add_setter(@columns[key], "visible", false) }
      add_breakpoint(narrow)
      @toasts = Adwaita::ToastOverlay.new
      @toasts.child = @split
      self.content = @toasts
    end

    def build_actions
      @application_menu = Gio::Menu.new
      {"open" => [nil, ["<Control>o"], -> { choose_file { |path| add_source(path) } }],
       "magnet" => [nil, ["<Control>l"], -> { prompt("Añadir magnet", "Enlace magnet", "magnet:?") { |source| add_source(source) } }],
       "search" => [nil, ["<Control>f"], -> { @search_bar.search_mode_enabled = !@search_bar.search_mode_enabled? }],
       "details" => [nil, ["F9"], -> { @details_split.show_sidebar = !@details_split.show_sidebar? }],
       "create" => ["Crear torrent…", [], -> { create_torrent }],
       "categories" => ["Nueva categoría…", [], -> { new_category }],
       "preferences" => ["Preferencias", ["<Control>comma"], -> { preferences }],
       "restart" => ["Reiniciar motor", [], -> { restart_engine }],
       "quit" => ["Salir", ["<Control>q"], -> { @app.quit_safely }]}.each do |name, (label, shortcuts, action)|
        simple = Gio::SimpleAction.new(name)
        simple.signal_connect("activate") { action.call }
        add_action(simple)
        @app.set_accels_for_action("win.#{name}", shortcuts)
        @application_menu.append(label, "win.#{name}") if label
      end
      @selection_menu = Gio::Menu.new
      {"properties" => ["Propiedades", -> { selected_ids.first.then { |id| show_details(id) if id } }],
       "recheck" => ["Verificar", -> { selected_action("recheck") }],
       "move" => ["Cambiar ubicación…", -> { choose_file(folder: true) { |path| selected_action("move", {"destination" => path}) } }],
       "remove" => ["Eliminar…", -> { remove_selected }]}.each do |name, (label, action)|
        simple = Gio::SimpleAction.new(name)
        simple.signal_connect("activate") { action.call }
        simple.enabled = false
        name == "properties" ? @properties_action = simple : @selection_actions << simple
        add_action(simple)
        @selection_menu.append(label, "win.#{name}")
      end
    end

    def menu_button(icon, label, menu)
      Gtk::MenuButton.new.tap do |widget|
        widget.icon_name = icon
        widget.tooltip_text = label
        widget.menu_model = menu
      end
    end

    def build_header
      header = @header = Adwaita::HeaderBar.new
      add_menu = Gio::Menu.new
      add_menu.append("Abrir torrent…", "win.open")
      add_menu.append("Añadir magnet…", "win.magnet")
      header.pack_start(menu_button("list-add-symbolic", "Añadir torrent o magnet", add_menu))
      @selection_controls = Gtk::Box.new(:horizontal, 0)
      @selection_controls.visible = false
      @pause_button = selection_button("media-playback-pause-symbolic", "Pausar selección") { selected_action("pause") }
      @resume_button = selection_button("media-playback-start-symbolic", "Reanudar selección") { selected_action("resume") }
      @selection_controls.append(@pause_button)
      @selection_controls.append(@resume_button)
      @selection_menu_button = menu_button("view-more-symbolic", "Acciones de la selección", @selection_menu)
      @selection_controls.append(@selection_menu_button)
      header.pack_start(@selection_controls)
      @details_toggle = Gtk::ToggleButton.new
      @details_toggle.icon_name = "sidebar-show-right-symbolic"
      @details_toggle.tooltip_text = "Mostrar detalles (F9)"
      @details_toggle.signal_connect("toggled") { @details_split.show_sidebar = @details_toggle.active? }
      header.pack_end(@details_toggle)
      @search_toggle = Gtk::ToggleButton.new
      @search_toggle.icon_name = "system-search-symbolic"
      @search_toggle.tooltip_text = "Buscar transferencias (Ctrl+F)"
      @search_toggle.signal_connect("toggled") { @search_bar.search_mode_enabled = @search_toggle.active? }
      header.pack_end(@search_toggle)
      compact_menu = Gio::Menu.new
      compact_menu.append("Detalles", "win.details")
      compact_menu.append_section(nil, @selection_menu)
      compact_menu.append_section(nil, @application_menu)
      @compact_menu = menu_button("open-menu-symbolic", "Menú principal", compact_menu)
      @compact_menu.visible = false
      header.pack_end(@compact_menu)
      header
    end

    def build_sidebar
      toolbar = Adwaita::ToolbarView.new
      header = Adwaita::HeaderBar.new
      header.pack_end(menu_button("open-menu-symbolic", "Menú principal", @application_menu))
      toolbar.add_top_bar(header)
      @sidebar = Gtk::ListBox.new
      @sidebar.add_css_class("navigation-sidebar")
      @sidebar.set_header_func do |row, _previous|
        if row.index == 5
          heading = padded(Gtk::Label.new("Categorías"))
          heading.xalign = 0
          heading.add_css_class("heading")
          row.header = heading
        else
          row.header = nil
        end
      end
      @sidebar.signal_connect("row-selected") do |_list, row|
        if row && !@rebuilding_sidebar
          @filter, @category = @navigation[row.index]
          @content_page.title = row.child.first_child.next_sibling.text
          @content_page.title = "Transferencias" if row.index.zero?
          @split.show_content = true
          refresh
        end
      end
      @sidebar.signal_connect("row-activated") { @split.show_content = true }
      rebuild_sidebar
      scroll = Gtk::ScrolledWindow.new
      scroll.hscrollbar_policy = :never
      scroll.child = @sidebar
      toolbar.content = scroll
      toolbar.add_bottom_bar(build_status)
      toolbar
    end

    def build_transfers
      toolbar = Adwaita::ToolbarView.new
      toolbar.add_css_class("view")
      @details_split = Adwaita::OverlaySplitView.new
      @details_split.sidebar_position = :end
      @details_split.min_sidebar_width = 280
      @details_split.max_sidebar_width = 320
      @details_split.show_sidebar = false
      toolbar.add_top_bar(build_header)
      @search_bar = Gtk::SearchBar.new
      @search = Gtk::SearchEntry.new
      @search.hexpand = true
      @search.placeholder_text = "Buscar transferencias"
      @search.signal_connect("search-changed") { refresh }
      @search_bar.child = @search
      @search_bar.connect_entry(@search)
      @search_bar.key_capture_widget = self
      @search_bar.signal_connect("notify::search-mode-enabled") do
        @search_toggle.active = @search_bar.search_mode_enabled?
        @search.text = "" unless @search_bar.search_mode_enabled?
      end
      toolbar.add_top_bar(@search_bar)
      @model = Gtk::StringList.new([])
      @selection = Gtk::MultiSelection.new(@model)
      @selection.signal_connect("selection-changed") { update_selection unless @updating_selection }
      @table = Gtk::ColumnView.new(@selection)
      @table.enable_rubberband = true
      @table.margin_start = @table.margin_end = 18
      @table.margin_top = 6
      @table.add_css_class("transfer-list")
      @table_style = Gtk::CssProvider.new
      @table_style.load_from_string(<<~CSS)
        columnview.transfer-list > listview > row { border-radius: 8px; margin: 2px 0; }
        columnview.transfer-list progressbar trough { min-width: 48px; }
      CSS
      Gtk::StyleContext.add_provider_for_display(display, @table_style, Gtk::StyleProvider::PRIORITY_APPLICATION)
      @columns = {}
      [["Nombre", "name", 260], ["Tamaño", "size", 90], ["Progreso", "progress", 160],
       ["Estado", "state", 150], ["Descarga", "download_rate", 105], ["Subida", "upload_rate", 105]].each do |title, key, width|
        factory = Gtk::SignalListItemFactory.new
        factory.signal_connect("setup") do |_factory, item|
          if key == "name"
            widget = Gtk::Box.new(:horizontal, 8)
            widget.append(Gtk::Image.new(icon_name: "text-x-generic-symbolic"))
            name = Gtk::Label.new("")
            name.xalign = 0
            name.hexpand = true
            name.ellipsize = :end
            widget.append(name)
          elsif key == "progress"
            widget = Gtk::Box.new(:horizontal, 8)
            progress = Gtk::ProgressBar.new
            progress.hexpand = true
            progress.valign = :center
            widget.append(progress)
            percentage = Gtk::Label.new("")
            percentage.xalign = 1
            percentage.width_chars = 6
            percentage.add_css_class("numeric")
            widget.append(percentage)
          else
            widget = Gtk::Label.new("")
            widget.xalign = %w[size download_rate upload_rate].include?(key) ? 1 : 0
            widget.ellipsize = :end
            widget.add_css_class("numeric") unless key == "state"
          end
          widget.margin_start = widget.margin_end = 12
          widget.margin_top = widget.margin_bottom = 6
          item.child = widget
        end
        factory.signal_connect("bind") do |_factory, item|
          row = JSON.parse(item.item.string)
          case key
          when "progress"
            item.child.first_child.fraction = row["progress"].clamp(0, 1)
            item.child.last_child.text = "#{(row['progress'] * 100).round(1)} %"
          when "name" then item.child.last_child.text = row["name"]
          when "state" then item.child.text = Format.state(row)
          when "size" then item.child.text = Format.bytes(row[key])
          when "download_rate", "upload_rate" then item.child.text = "#{Format.bytes(row[key])}/s"
          else item.child.text = row[key]
          end
          item.child.tooltip_text = item.child.is_a?(Gtk::Label) ? item.child.text : item.child.last_child.text
        end
        column = Gtk::ColumnViewColumn.new(title, factory)
        column.resizable = true
        column.fixed_width = width
        column.expand = key == "name"
        # The catalog sorts each snapshot; columns provide the native sort controls.
        column.sorter = Gtk::StringSorter.new(nil)
        @columns[key] = column
        @table.append_column(column)
      end
      @table.sort_by_column(@columns["name"], :ascending)
      @table.sorter.signal_connect("changed") do |sorter|
        @sort_key = @columns.key(sorter.primary_sort_column) || "name"
        @sort_descending = sorter.primary_sort_order == Gtk::SortType::DESCENDING
        refresh
      end
      @table.signal_connect("activate") { |_view, position| show_details(@rows[position]["id"]) }
      scroll = Gtk::ScrolledWindow.new
      scroll.vexpand = true
      scroll.child = @table
      @content_stack = Gtk::Stack.new
      @content_stack.add_named(scroll, "table")
      @empty = Adwaita::StatusPage.new
      @empty.icon_name = "folder-download-symbolic"
      @empty.title = "No hay transferencias"
      @empty.description = "Abre un torrent o añade un enlace magnet para empezar."
      @clear_filters = button("Mostrar todas las transferencias") { clear_filters }
      @clear_filters.halign = :center
      @empty.child = @clear_filters
      @content_stack.add_named(@empty, "empty")
      @details_split.content = @content_stack
      @details_split.sidebar = build_summary
      @details_split.signal_connect("notify::show-sidebar") { @details_toggle.active = @details_split.show_sidebar? }
      toolbar.content = @details_split
      toolbar
    end

    def build_summary
      pane = box(0)
      heading = padded(Gtk::Box.new(:horizontal, 12))
      caption = Gtk::Label.new("Detalles")
      caption.xalign = 0
      caption.hexpand = true
      caption.add_css_class("heading")
      heading.append(caption)
      close = icon_button("window-close-symbolic", "Ocultar detalles (F9)") { @details_split.show_sidebar = false }
      close.add_css_class("flat")
      heading.append(close)
      pane.append(heading)
      @summary_stack = Gtk::Stack.new
      @summary_stack.vexpand = true
      @summary = padded(box(18), 18)
      @summary.visible = false
      @summary_name = Gtk::Label.new("")
      @summary_name.xalign = 0
      @summary_name.wrap = true
      @summary_name.add_css_class("heading")
      @summary.append(@summary_name)
      @summary_progress = Gtk::ProgressBar.new
      @summary.append(@summary_progress)
      @summary_state = Gtk::Label.new("")
      @summary_state.xalign = 0
      @summary_state.wrap = true
      @summary_state.add_css_class("dim-label")
      @summary.append(@summary_state)
      group = Adwaita::PreferencesGroup.new
      group.title = "Transferencia"
      @summary_metrics = %w[Descarga Subida Pares Restante].map do |title|
        row = Adwaita::ActionRow.new
        row.title = title
        value = Gtk::Label.new("—")
        value.add_css_class("dim-label")
        row.add_suffix(value)
        group.add(row)
        value
      end
      @summary.append(group)
      @summary_destination = Adwaita::ActionRow.new
      @summary_destination.title = "Carpeta de destino"
      @summary_destination.use_markup = false
      @summary_destination.subtitle_lines = 2
      @summary_destination.subtitle_selectable = true
      location = Adwaita::PreferencesGroup.new
      location.add(@summary_destination)
      @summary.append(location)
      @properties = button("Propiedades") { selected_ids.first.then { |id| show_details(id) if id } }
      @summary.append(@properties)
      scroll = Gtk::ScrolledWindow.new
      scroll.hscrollbar_policy = :never
      scroll.child = @summary
      @summary_stack.add_named(scroll, "summary")
      empty = Adwaita::StatusPage.new
      empty.icon_name = "dialog-information-symbolic"
      empty.title = "Sin selección"
      empty.description = "Selecciona una transferencia para ver sus detalles."
      @summary_stack.add_named(empty, "empty")
      pane.append(@summary_stack)
      pane
    end

    def build_status
      status = padded(box(8), 12)
      @status = Gtk::Label.new("Preparando motor…")
      @status.xalign = 0
      @status.ellipsize = :end
      @status.add_css_class("dim-label")
      @status.add_css_class("caption")
      status.append(@status)
      rates = Gtk::Box.new(:horizontal, 12)
      @download_status = Gtk::Label.new("↓ 0 B/s")
      @upload_status = Gtk::Label.new("↑ 0 B/s")
      [@download_status, @upload_status].each do |label|
        label.xalign = 0
        label.hexpand = true
        label.add_css_class("caption")
        label.add_css_class("dim-label")
        rates.append(label)
      end
      status.append(rates)
      status
    end

    def rebuild_sidebar
      @rebuilding_sidebar = true
      while (child = @sidebar.first_child)
        @sidebar.remove(child)
      end
      @navigation = [["all", nil], ["downloading", nil], ["seeding", nil], ["paused", nil], ["error", nil]]
      items = [["Todas", "view-list-symbolic"], ["Descargando", "folder-download-symbolic"],
        ["Compartiendo", "folder-publicshare-symbolic"], ["En pausa", "media-playback-pause-symbolic"], ["Con errores", "dialog-warning-symbolic"]]
      @app.settings["categories"].each { |category| @navigation << ["all", category]; items << [category, "folder-symbolic"] }
      @sidebar_counts = items.map do |name, icon|
        row = padded(Gtk::Box.new(:horizontal, 10), 8)
        row.append(Gtk::Image.new(icon_name: icon))
        label = Gtk::Label.new(name)
        label.xalign = 0
        label.hexpand = true
        label.ellipsize = :end
        row.append(label)
        count = Gtk::Label.new("0")
        count.add_css_class("dim-label")
        row.append(count)
        @sidebar.append(row)
        row.parent.tooltip_text = name
        count
      end
      index = @navigation.index([@filter, @category]) || 0
      @sidebar.select_row(@sidebar.get_row_at_index(index))
      @rebuilding_sidebar = false
      update_sidebar_counts(@all_rows || [])
    end

    def update_sidebar_counts(rows)
      transfers = Transfers.new(@app.engine)
      @navigation.each_with_index do |(filter, category), index|
        @sidebar_counts[index].text = transfers.select(rows, filter: filter, category: category).size.to_s
      end
    end

    def clear_filters
      @search.text = ""
      @sidebar.select_row(@sidebar.get_row_at_index(0))
      refresh
    end

    def update_selection
      selected = @rows.select.with_index { |_row, index| @selection.selected?(index) }
      @selection_buttons.each { |widget| widget.sensitive = selected.any? }
      @selection_actions.each { |action| action.enabled = selected.any? }
      @selection_controls.visible = selected.any?
      @pause_button.visible = @pause_button.sensitive = selected.any? { |row| !row["paused"] }
      @resume_button.visible = @resume_button.sensitive = selected.any? { |row| row["paused"] }
      @summary_stack.visible_child_name = selected.any? ? "summary" : "empty"
      @summary.visible = selected.any?
      @properties_action.enabled = selected.size == 1
      return if selected.empty?
      single = selected.size == 1
      row = selected.first
      @properties.sensitive = single
      @summary_name.text = single ? row["name"] : "#{selected.size} transferencias seleccionadas"
      @summary_name.tooltip_text = @summary_name.text
      size = selected.sum { |item| item["size"] }
      done = selected.sum { |item| item["done"] }
      progress = single ? row["progress"] : size.positive? ? done.to_f / size : 0
      @summary_progress.fraction = progress.clamp(0, 1)
      state = single ? Format.state(row) : "Selección múltiple"
      @summary_state.text = "#{state} · #{(progress * 100).round(1)} % · #{Format.bytes(done)} de #{Format.bytes(size)}"
      @summary_state.tooltip_text = @summary_state.text
      @summary_metrics[0].text = "#{Format.bytes(selected.sum { |item| item['download_rate'] })}/s"
      @summary_metrics[1].text = "#{Format.bytes(selected.sum { |item| item['upload_rate'] })}/s"
      @summary_metrics[2].text = selected.sum { |item| item["peers"] }.to_s
      @summary_metrics[3].text = single && row["eta"] >= 0 ? "#{row['eta'] / 60} min" : "—"
      @summary_destination.visible = single
      @summary_destination.subtitle = single ? row["destination"] : ""
      @summary_destination.tooltip_text = @summary_destination.subtitle
    end

    def selected_ids
      @rows.each_index.select { |i| @selection.selected?(i) }.map { |i| @rows[i]["id"] }
    end

    def refresh
      return unless @search && @summary
      if @busy
        @refresh_pending = true
        return
      end
      @busy = true
      query, filter, category = @search.text, @filter, @category
      sort, descending = @sort_key, @sort_descending
      @app.async(->(result) {
        all_rows, rows = result
        ids = selected_ids
        @updating_selection = true
        @all_rows = all_rows
        @rows = rows
        @model.splice(0, @model.n_items, rows.map { |row| JSON.generate(row) })
        @selection.unselect_all
        rows.each_with_index { |row, i| @selection.select_item(i, false) if ids.include?(row["id"]) }
        @updating_selection = false
        update_selection
        update_sidebar_counts(all_rows)
        @content_stack.visible_child_name = rows.empty? ? "empty" : "table"
        @empty.title = all_rows.empty? ? "No hay transferencias" : "No hay coincidencias"
        @empty.description = all_rows.empty? ? "Abre un torrent o añade un enlace magnet para empezar." : "Prueba otro nombre o cambia los filtros."
        @clear_filters.visible = all_rows.any?
        @status.text = rows.size == all_rows.size ? Format.transfers(all_rows.size) : "#{rows.size} de #{Format.transfers(all_rows.size)}"
        @download_status.text = "↓ #{Format.bytes(all_rows.sum { |row| row['download_rate'] })}/s"
        @upload_status.text = "↑ #{Format.bytes(all_rows.sum { |row| row['upload_rate'] })}/s"
        @busy = false
        if @refresh_pending
          @refresh_pending = false
          refresh
        end
      }) do
        begin
          transfers = Transfers.new(@app.engine)
          all_rows = transfers.list
          rows = transfers.select(all_rows, query: query, filter: filter, category: category, sort: sort, descending: descending)
          events = @app.engine.events
          events.select { |event| event["event"] == "error" }.each do |event|
            GLib::Idle.add { error(event["data"].to_s); false }
          end
          [all_rows, rows]
        rescue StandardError
          GLib::Idle.add { @busy = false; false }
          raise
        end
      end
    end

    def selected_action(method, params = {})
      selected = @rows.select.with_index { |_row, index| @selection.selected?(index) }
      selected = selected.reject { |row| row["paused"] } if method == "pause"
      selected = selected.select { |row| row["paused"] } if method == "resume"
      ids = selected.map { |row| row["id"] }
      return if ids.empty?
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
      window = Adwaita::Dialog.new
      @dialogs ||= []
      @dialogs << window
      window.signal_connect("closed") { @dialogs.delete(window) }
      window.title = title
      window.content_width = width
      window.content_height = 500
      toolbar = Adwaita::ToolbarView.new
      toolbar.add_top_bar(Adwaita::HeaderBar.new)
      body = padded(box(18), 24)
      clamp = Adwaita::Clamp.new
      clamp.maximum_size = 680
      clamp.child = body
      scroll = Gtk::ScrolledWindow.new
      scroll.hscrollbar_policy = :never
      scroll.child = clamp
      scroll.vexpand = true
      toolbar.content = scroll
      window.child = toolbar
      yield window, body
      window.present(self)
      window
    end

    def entry(body, label, value = "")
      list = Gtk::ListBox.new
      list.selection_mode = :none
      list.add_css_class("boxed-list")
      body.append(list)
      Adwaita::EntryRow.new.tap do |widget|
        widget.title = label
        widget.text = value.to_s
        widget.tooltip_text = label
        list.append(widget)
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
        win.signal_connect("closed") do
          GLib::Source.remove(timer) unless file_controls
          @app.async { @app.engine.request("remove", {"torrent" => id}) } unless committed
          false
        end
      end
    end

    def priority_controls(body, files)
      list = Gtk::ListBox.new
      list.selection_mode = :none
      list.add_css_class("boxed-list")
      body.append(list)
      files.map do |file|
        row = Adwaita::ActionRow.new
        row.use_markup = false
        row.title = file["path"]
        row.title_lines = 2
        row.subtitle = Format.bytes(file["size"])
        control = Gtk::DropDown.new(["Omitir", "1", "2", "3", "Normal", "5", "6", "Alta"])
        control.selected = file["padding"] ? 0 : file["priority"]
        control.sensitive = !file["padding"]
        control.valign = :center
        row.add_suffix(control)
        row.activatable_widget = control
        list.append(row)
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
      dialog("Eliminar #{Format.transfers(ids.size)}") do |win, body|
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
      win = Adwaita::PreferencesDialog.new
      win.title = "Preferencias"
      win.content_width = 560
      win.content_height = 620
      @dialogs ||= []
      @dialogs << win
      win.signal_connect("closed") { @dialogs.delete(win) }
      page = Adwaita::PreferencesPage.new
      fields = {}
      [["Velocidad", "Un valor de 0 significa sin límite.", {"download" => "Descarga (B/s)", "upload" => "Subida (B/s)"}],
       ["Transferencias activas", "Un valor de 0 detiene esa clase de transferencias.", {"active_downloads" => "Descargas simultáneas", "active_seeds" => "Torrents compartidos"}]].each do |title, description, labels|
        group = Adwaita::PreferencesGroup.new
        group.title = title
        group.description = description
        labels.each do |key, label|
          field = Adwaita::EntryRow.new
          field.title = label
          field.text = @app.settings["limits"][key].to_s
          field.input_purpose = :digits
          fields[key] = field
          group.add(field)
        end
        page.add(group)
      end
      footer = Adwaita::PreferencesGroup.new
      footer.description = "Al cerrar la ventana, las transferencias continúan. Usa Salir para detener el cliente."
      save = button("Guardar") do
        begin
          values = fields.transform_values { |field| Integer(field.text) }
          raise ArgumentError if values.values.any?(&:negative?)
          @app.async(->(_) { @app.settings["limits"] = values; @app.save_settings; win.close }) { @app.engine.request("limits", values) }
        rescue ArgumentError
          error("Usa números enteros mayores o iguales a cero")
        end
      end
      save.halign = :end
      save.add_css_class("suggested-action")
      footer.add(save)
      page.add(footer)
      win.add(page)
      win.present(self)
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

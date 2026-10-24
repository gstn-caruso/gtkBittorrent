require "json"
require "fileutils"

module GtkBitTorrent
  class Store
    attr_reader :state_dir, :config_dir

    def initialize(env = ENV)
      @home = env.fetch("HOME")
      @user_dirs = File.join(env.fetch("XDG_CONFIG_HOME", File.join(@home, ".config")), "user-dirs.dirs")
      @state_dir = File.join(env.fetch("XDG_STATE_HOME", File.join(env.fetch("HOME"), ".local/state")), "gtkbittorrent")
      @config_dir = File.join(env.fetch("XDG_CONFIG_HOME", File.join(env.fetch("HOME"), ".config")), "gtkbittorrent")
      [state_dir, config_dir].each { |dir| FileUtils.mkdir_p(dir, mode: 0o700) }
    end

    def load
      path = File.join(config_dir, "preferences.json")
      [path, "#{path}.previous"].each do |candidate|
        next unless File.file?(candidate)
        begin
          value = JSON.parse(File.read(candidate))
          raise JSON::ParserError, "Invalid settings" unless valid_value?(value)
          return value
        rescue JSON::ParserError
          next
        end
      end
      raise "Preferencias dañadas: restaure preferences.json o su checkpoint .previous" if File.exist?(path) || File.exist?("#{path}.previous")
      {"categories" => [], "destination" => downloads_dir, "limits" => {"download" => 0, "upload" => 0, "active_downloads" => 3, "active_seeds" => 5}}
    end

    def save(value)
      path = File.join(config_dir, "preferences.json")
      temp = "#{path}.tmp.#{$$}"
      File.open(temp, File::WRONLY | File::CREAT | File::TRUNC, 0o600) do |file|
        file.write(JSON.pretty_generate(value))
        file.flush
        file.fsync
      end
      FileUtils.cp(path, "#{path}.previous") if File.file?(path) && valid?(path)
      File.rename(temp, path)
      File.open(config_dir) { |dir| dir.fsync }
    ensure
      File.unlink(temp) if temp && File.exist?(temp)
    end

    private

    def downloads_dir
      if File.file?(@user_dirs)
        value = File.read(@user_dirs)[/^XDG_DOWNLOAD_DIR="([^"]+)"$/, 1]
        return value.sub("$HOME", @home) if value && (value.start_with?("/") || value.start_with?("$HOME/"))
      end
      File.join(@home, "Downloads")
    end

    def valid?(path)
      valid_value?(JSON.parse(File.read(path)))
    rescue JSON::ParserError
      false
    end

    def valid_value?(value)
      value.is_a?(Hash) && value["categories"].is_a?(Array) && value["categories"].all? { |category| category.is_a?(String) } &&
        value["destination"].is_a?(String) && value["limits"].is_a?(Hash) &&
        %w[download upload active_downloads active_seeds].all? { |key| value["limits"][key].is_a?(Integer) && value["limits"][key] >= 0 }
    end
  end
end

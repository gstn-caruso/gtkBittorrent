require "open3"
require "json"
require "timeout"
require_relative "version"

module GtkBitTorrent
  class EngineError < StandardError
    attr_reader :code

    def initialize(code, message)
      @code = code
      super(message)
    end
  end

  class EngineClient
    def initialize(state_dir:, executable: ENV.fetch("GTKB_ENGINE", File.expand_path("../../build/gtkbittorrent-engine", __dir__)), **options)
      @mutex = Mutex.new
      @pending = {}
      @next_id = 0
      @events = Queue.new
      @log = File.open(File.join(state_dir, "engine.log"), "a", 0o600)
      args = [executable, "--state-dir", state_dir]
      options.each { |key, value| args.concat(["--#{key.to_s.tr('_', '-')}", value.to_s]) }
      @input, @output, @wait = Open3.popen2(*args, err: @log)
      @reader = Thread.new { read_messages }
      hello = request("hello")
      raise EngineError.new("version", "Versiones incompatibles de aplicación y motor") unless hello["version"] == VERSION
    rescue StandardError
      close rescue nil
      raise
    end

    def request(method, params = {}, timeout: 45)
      response = Queue.new
      id = @mutex.synchronize do
        raise EngineError.new("engine_stopped", "El motor se detuvo; reinicie para recuperar el checkpoint") unless @wait.alive?
        @next_id += 1
        @pending[@next_id] = response
        @input.puts(JSON.generate({v: 1, id: @next_id, method: method, params: params}))
        @input.flush
        @next_id
      end
      message = Timeout.timeout(timeout) { response.pop }
      raise EngineError.new(message["error"]["code"], message["error"]["message"]) if message["error"]
      message.fetch("result")
    rescue Timeout::Error
      raise EngineError.new("timeout", "El motor no respondió a #{method}")
    ensure
      @mutex.synchronize { @pending.delete(id) } if id
    end

    def events
      result = []
      result << @events.pop(true) until @events.empty?
      result
    end

    def close
      return if @closed
      request("shutdown") if @wait&.alive?
    ensure
      @closed = true
      @input&.close unless @input&.closed?
      if @wait && !@wait.join(10)
        Process.kill("TERM", @wait.pid)
        @wait.join(5)
      end
      @output&.close unless @output&.closed?
      @log&.close unless @log&.closed?
    end

    private

    def read_messages
      @output.each_line do |line|
        message = JSON.parse(line)
        raise "Protocolo incompatible" unless message["v"] == 1
        if message.key?("id")
          @mutex.synchronize { @pending[message["id"]]&.push(message) }
        else
          @events.push(message)
        end
      end
    rescue IOError, JSON::ParserError => error
      @events.push({"event" => "error", "data" => error.message})
    ensure
      @mutex.synchronize do
        @pending.each_value { |queue| queue.push({"error" => {"code" => "engine_stopped", "message" => "El motor se detuvo"}}) }
      end
    end
  end
end

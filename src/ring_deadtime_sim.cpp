#include <algorithm>
#include <cmath>
#include <cstdint>
#include <deque>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <queue>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

enum class EventKind : int {
  Arrival = 0,
  Maturity = 1,
  SerializerEnd = 2,
  ServiceEnd = 3,
  LegacyRecordReady = 4,
};

struct Config {
  std::string architecture = "ring";
  double clock_hz = 62.5e6;
  int channels = 40;
  int lanes = 2;
  int channels_per_lane = 20;
  int rate_start = 1000;
  int rate_stop = 14000;
  int points = 8;
  std::vector<int> rate_list;
  std::uint64_t reset_cycles = 8;
  std::uint64_t warmup_cycles = 20000;
  std::uint64_t measure_cycles = 200000;
  int repeats = 3;
  int seed_start = 101;
  int seed_step = 1000;
  int frame_samples = 512;
  int pretrigger_samples = 64;
  int ring_depth = 2048;
  int queue_depth = 4;
  int overlap_granularity = 16;
  int signal_delay_steps = 0;
  int record_words = 120;
  int serializer_cycles = 648;
  int builder_busy_cycles = 525;
  int prog_empty_thresh = 220;
  int prog_full_thresh = 200;
  std::string csv_out;
  std::string raw_csv_out;
};

struct Event {
  std::uint64_t time = 0;
  EventKind kind = EventKind::Arrival;
  std::uint64_t seq = 0;
  int channel = 0;
};

struct EventCompare {
  bool operator()(const Event &lhs, const Event &rhs) const {
    if (lhs.time != rhs.time) {
      return lhs.time > rhs.time;
    }
    if (lhs.kind != rhs.kind) {
      return static_cast<int>(lhs.kind) > static_cast<int>(rhs.kind);
    }
    return lhs.seq > rhs.seq;
  }
};

struct PendingFrame {
  std::uint64_t sample0_ts = 0;
  std::uint64_t end_ts = 0;
  std::uint64_t maturity_time = 0;
};

struct Service {
  int channel = 0;
  int words = 0;
  std::uint64_t start = 0;
  std::uint64_t end = 0;
};

struct ChannelState {
  std::deque<PendingFrame> queue;
  bool serializer_active = false;
  std::uint64_t active_sample0_ts = 0;
  std::uint64_t active_end_ts = 0;
  int active_record_words = 0;
  std::uint64_t serializer_end = 0;
  std::uint64_t busy_until = 0;
  bool last_trigger_valid = false;
  std::uint64_t last_trigger_ts = 0;
  std::deque<int> completed_record_words;
  int completed_words = 0;
  bool coverage_valid = false;
  std::uint64_t coverage_end_ts = 0;
};

struct LaneState {
  int channel_base = 0;
  int rr_sel = 0;
  std::optional<Service> current_service;
};

struct RunStats {
  int rate_hz_per_channel = 0;
  int repeat_index = 0;
  int signal_delay_steps = 0;
  std::uint64_t generated_total = 0;
  std::uint64_t accepted_total = 0;
  std::uint64_t sent_total = 0;
  std::uint64_t sent_word_total = 0;
  std::uint64_t busy_counter_total = 0;
  std::uint64_t full_counter_total = 0;
  std::uint64_t spacing_counter_total = 0;
  std::uint64_t queue_counter_total = 0;
  std::uint64_t ring_counter_total = 0;
  std::uint64_t output_counter_total = 0;
  std::uint64_t dead_ppm = 0;
  double dead_fraction = 0.0;
};

struct SummaryRow {
  int rate_hz_per_channel = 0;
  int repeats = 0;
  double generated_total_mean = 0.0;
  double generated_total_std = 0.0;
  double accepted_total_mean = 0.0;
  double accepted_total_std = 0.0;
  double sent_total_mean = 0.0;
  double sent_total_std = 0.0;
  double sent_word_total_mean = 0.0;
  double sent_word_total_std = 0.0;
  double busy_counter_total_mean = 0.0;
  double busy_counter_total_std = 0.0;
  double full_counter_total_mean = 0.0;
  double full_counter_total_std = 0.0;
  double spacing_counter_total_mean = 0.0;
  double spacing_counter_total_std = 0.0;
  double queue_counter_total_mean = 0.0;
  double queue_counter_total_std = 0.0;
  double ring_counter_total_mean = 0.0;
  double ring_counter_total_std = 0.0;
  double output_counter_total_mean = 0.0;
  double output_counter_total_std = 0.0;
  double dead_fraction_mean = 0.0;
  double dead_fraction_std = 0.0;
};

std::string join_csv(const std::vector<std::string> &parts) {
  std::ostringstream out;
  for (std::size_t i = 0; i < parts.size(); ++i) {
    if (i > 0) {
      out << ',';
    }
    out << parts[i];
  }
  return out.str();
}

std::vector<std::string> split_csv(const std::string &text) {
  std::vector<std::string> out;
  std::stringstream ss(text);
  std::string item;
  while (std::getline(ss, item, ',')) {
    if (!item.empty()) {
      out.push_back(item);
    }
  }
  return out;
}

int parse_int(const std::string &value, const std::string &name) {
  try {
    std::size_t pos = 0;
    int parsed = std::stoi(value, &pos, 10);
    if (pos != value.size()) {
      throw std::invalid_argument("trailing characters");
    }
    return parsed;
  } catch (const std::exception &) {
    throw std::runtime_error("invalid integer for " + name + ": " + value);
  }
}

double parse_double(const std::string &value, const std::string &name) {
  try {
    std::size_t pos = 0;
    double parsed = std::stod(value, &pos);
    if (pos != value.size()) {
      throw std::invalid_argument("trailing characters");
    }
    return parsed;
  } catch (const std::exception &) {
    throw std::runtime_error("invalid float for " + name + ": " + value);
  }
}

void print_help(std::ostream &os) {
  os << "Usage: ring_deadtime_sim [options]\n\n"
     << "Stochastic ring-builder dead-time model aligned with the current\n"
     << "ring-buffer HDL acceptance rules.\n\n"
     << "Options:\n"
     << "  --rate-list CSV               Comma-separated per-channel rates in Hz\n"
     << "  --architecture NAME          legacy, ring, or coalesced (default: ring)\n"
     << "  --rate-start N               Sweep start rate in Hz/channel\n"
     << "  --rate-stop N                Sweep stop rate in Hz/channel\n"
     << "  --points N                   Number of linear sweep points\n"
     << "  --repeats N                  Repeats per rate point\n"
     << "  --reset-cycles N             Reset cycles before arrivals\n"
     << "  --warmup-cycles N            Warmup cycles before counting stats\n"
     << "  --measure-cycles N           Measured cycles after warmup\n"
     << "  --seed-start N               Base RNG seed\n"
     << "  --seed-step N                Seed offset per repeat\n"
     << "  --clock-hz F                 Clock frequency in Hz\n"
     << "  --channels N                 Total channel count\n"
     << "  --lanes N                    Lane count\n"
     << "  --channels-per-lane N        Channels per lane\n"
     << "  --frame-samples N            Frame sample count\n"
     << "  --pretrigger-samples N       Pretrigger sample count\n"
     << "  --ring-depth N               Ring depth in samples\n"
     << "  --queue-depth N              Pending frame queue depth\n"
     << "  --signal-delay-steps N       Overlap control in 16-sample steps\n"
     << "  --record-words N             Words per serialized record\n"
     << "  --serializer-cycles N        Cycles from serializer start to record completion\n"
     << "  --builder-busy-cycles N      Accepted-trigger busy time for legacy mode\n"
     << "  --prog-empty-thresh N        FIFO prog_empty threshold in words\n"
     << "  --prog-full-thresh N         FIFO prog_full threshold in words\n"
     << "  --csv-out PATH               Summary CSV output\n"
     << "  --raw-csv-out PATH           Raw per-run CSV output\n"
     << "  --help                       Show this help\n";
}

Config parse_args(int argc, char **argv) {
  Config cfg;
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    auto require_value = [&](const std::string &name) -> std::string {
      if (i + 1 >= argc) {
        throw std::runtime_error("missing value after " + name);
      }
      return argv[++i];
    };

    if (arg == "--help" || arg == "-h") {
      print_help(std::cout);
      std::exit(0);
    } else if (arg == "--architecture") {
      cfg.architecture = require_value(arg);
    } else if (arg == "--rate-list") {
      cfg.rate_list.clear();
      for (const auto &item : split_csv(require_value(arg))) {
        cfg.rate_list.push_back(parse_int(item, arg));
      }
    } else if (arg == "--rate-start") {
      cfg.rate_start = parse_int(require_value(arg), arg);
    } else if (arg == "--rate-stop") {
      cfg.rate_stop = parse_int(require_value(arg), arg);
    } else if (arg == "--points") {
      cfg.points = parse_int(require_value(arg), arg);
    } else if (arg == "--repeats") {
      cfg.repeats = parse_int(require_value(arg), arg);
    } else if (arg == "--reset-cycles") {
      cfg.reset_cycles = static_cast<std::uint64_t>(parse_int(require_value(arg), arg));
    } else if (arg == "--warmup-cycles") {
      cfg.warmup_cycles = static_cast<std::uint64_t>(parse_int(require_value(arg), arg));
    } else if (arg == "--measure-cycles") {
      cfg.measure_cycles = static_cast<std::uint64_t>(parse_int(require_value(arg), arg));
    } else if (arg == "--seed-start") {
      cfg.seed_start = parse_int(require_value(arg), arg);
    } else if (arg == "--seed-step") {
      cfg.seed_step = parse_int(require_value(arg), arg);
    } else if (arg == "--clock-hz") {
      cfg.clock_hz = parse_double(require_value(arg), arg);
    } else if (arg == "--channels") {
      cfg.channels = parse_int(require_value(arg), arg);
    } else if (arg == "--lanes") {
      cfg.lanes = parse_int(require_value(arg), arg);
    } else if (arg == "--channels-per-lane") {
      cfg.channels_per_lane = parse_int(require_value(arg), arg);
    } else if (arg == "--frame-samples") {
      cfg.frame_samples = parse_int(require_value(arg), arg);
    } else if (arg == "--pretrigger-samples") {
      cfg.pretrigger_samples = parse_int(require_value(arg), arg);
    } else if (arg == "--ring-depth") {
      cfg.ring_depth = parse_int(require_value(arg), arg);
    } else if (arg == "--queue-depth") {
      cfg.queue_depth = parse_int(require_value(arg), arg);
    } else if (arg == "--signal-delay-steps") {
      cfg.signal_delay_steps = parse_int(require_value(arg), arg);
    } else if (arg == "--record-words") {
      cfg.record_words = parse_int(require_value(arg), arg);
    } else if (arg == "--serializer-cycles") {
      cfg.serializer_cycles = parse_int(require_value(arg), arg);
    } else if (arg == "--builder-busy-cycles") {
      cfg.builder_busy_cycles = parse_int(require_value(arg), arg);
    } else if (arg == "--prog-empty-thresh") {
      cfg.prog_empty_thresh = parse_int(require_value(arg), arg);
    } else if (arg == "--prog-full-thresh") {
      cfg.prog_full_thresh = parse_int(require_value(arg), arg);
    } else if (arg == "--csv-out") {
      cfg.csv_out = require_value(arg);
    } else if (arg == "--raw-csv-out") {
      cfg.raw_csv_out = require_value(arg);
    } else {
      throw std::runtime_error("unknown option: " + arg);
    }
  }

  if (cfg.channels != cfg.lanes * cfg.channels_per_lane) {
    throw std::runtime_error("channels must equal lanes * channels-per-lane");
  }
  if (cfg.architecture != "ring" && cfg.architecture != "legacy" && cfg.architecture != "coalesced") {
    throw std::runtime_error("architecture must be 'legacy', 'ring', or 'coalesced'");
  }
  if (cfg.points < 1 || cfg.repeats < 1) {
    throw std::runtime_error("points and repeats must be positive");
  }
  if (cfg.signal_delay_steps < 0 || cfg.signal_delay_steps > 31) {
    throw std::runtime_error("signal-delay-steps must be in [0, 31]");
  }
  if (cfg.queue_depth < 1 || cfg.ring_depth <= cfg.frame_samples) {
    throw std::runtime_error("queue-depth must be positive and ring-depth must exceed frame-samples");
  }
  if (cfg.frame_samples < 1 || cfg.record_words < 1 || cfg.serializer_cycles < 1) {
    throw std::runtime_error("frame, record, and serializer parameters must be positive");
  }
  return cfg;
}

std::vector<int> sweep_rates(const Config &cfg) {
  if (!cfg.rate_list.empty()) {
    return cfg.rate_list;
  }
  if (cfg.points == 1) {
    return {cfg.rate_start};
  }
  std::vector<int> rates;
  rates.reserve(static_cast<std::size_t>(cfg.points));
  const double step = static_cast<double>(cfg.rate_stop - cfg.rate_start) / static_cast<double>(cfg.points - 1);
  for (int idx = 0; idx < cfg.points; ++idx) {
    rates.push_back(static_cast<int>(std::llround(static_cast<double>(cfg.rate_start) + step * idx)));
  }
  return rates;
}

double mean(const std::vector<double> &values) {
  if (values.empty()) {
    return 0.0;
  }
  double sum = 0.0;
  for (double value : values) {
    sum += value;
  }
  return sum / static_cast<double>(values.size());
}

double stddev(const std::vector<double> &values) {
  if (values.size() <= 1U) {
    return 0.0;
  }
  const double mu = mean(values);
  double accum = 0.0;
  for (double value : values) {
    const double diff = value - mu;
    accum += diff * diff;
  }
  return std::sqrt(accum / static_cast<double>(values.size() - 1U));
}

struct Simulator {
  explicit Simulator(const Config &cfg_in, int rate_in, int repeat_idx_in)
      : cfg(cfg_in),
        rate_hz_per_channel(rate_in),
        repeat_index(repeat_idx_in),
        total_cycles(cfg.reset_cycles + cfg.warmup_cycles + cfg.measure_cycles),
        measure_lo(cfg.reset_cycles + cfg.warmup_cycles),
        measure_hi(cfg.reset_cycles + cfg.warmup_cycles + cfg.measure_cycles),
        overlap_samples(std::min(cfg.signal_delay_steps * cfg.overlap_granularity, cfg.frame_samples - 1)),
        min_trigger_spacing(cfg.frame_samples - overlap_samples),
        ring_safe_margin(cfg.ring_depth - cfg.frame_samples),
        channels(static_cast<std::size_t>(cfg.channels)),
        lanes(static_cast<std::size_t>(cfg.lanes)),
        p(rate_hz_per_channel <= 0 ? 0.0 : static_cast<double>(rate_hz_per_channel) / cfg.clock_hz),
        rng(static_cast<std::mt19937_64::result_type>(cfg.seed_start + repeat_index * cfg.seed_step + rate_hz_per_channel)),
        geometric(p > 0.0 ? p : std::numeric_limits<double>::min()) {
    for (int lane = 0; lane < cfg.lanes; ++lane) {
      lanes[static_cast<std::size_t>(lane)].channel_base = lane * cfg.channels_per_lane;
    }
  }

  RunStats run() {
    schedule_initial_arrivals();
    while (!events.empty()) {
      const Event event = events.top();
      events.pop();
      if (event.time > total_cycles) {
        break;
      }

      switch (event.kind) {
        case EventKind::Arrival:
          handle_arrival(event);
          break;
        case EventKind::Maturity:
          handle_maturity(event);
          break;
        case EventKind::SerializerEnd:
          handle_serializer_end(event);
          break;
        case EventKind::ServiceEnd:
          handle_service_end(event);
          break;
        case EventKind::LegacyRecordReady:
          handle_legacy_record_ready(event);
          break;
      }
    }

    RunStats out;
    out.rate_hz_per_channel = rate_hz_per_channel;
    out.repeat_index = repeat_index;
    out.signal_delay_steps = cfg.signal_delay_steps;
    out.generated_total = generated_total;
    out.accepted_total = accepted_total;
    out.sent_total = sent_total;
    out.sent_word_total = sent_word_total;
    out.busy_counter_total = busy_total;
    out.full_counter_total = full_total;
    out.spacing_counter_total = spacing_total;
    out.queue_counter_total = queue_total;
    out.ring_counter_total = ring_total;
    out.output_counter_total = output_total;

    const std::uint64_t lost = generated_total > accepted_total ? (generated_total - accepted_total) : 0ULL;
    if (generated_total > 0ULL) {
      out.dead_ppm = static_cast<std::uint64_t>(
          std::llround((static_cast<long double>(lost) * 1000000.0L) / static_cast<long double>(generated_total)));
      out.dead_fraction = static_cast<double>(lost) / static_cast<double>(generated_total);
    }
    return out;
  }

 private:
  const Config &cfg;
  int rate_hz_per_channel = 0;
  int repeat_index = 0;
  std::uint64_t total_cycles = 0;
  std::uint64_t measure_lo = 0;
  std::uint64_t measure_hi = 0;
  int overlap_samples = 0;
  int min_trigger_spacing = 0;
  int ring_safe_margin = 0;
  std::vector<ChannelState> channels;
  std::vector<LaneState> lanes;
  double p = 0.0;
  std::mt19937_64 rng;
  std::geometric_distribution<std::uint64_t> geometric;
  std::priority_queue<Event, std::vector<Event>, EventCompare> events;
  std::uint64_t event_seq = 0;

  std::uint64_t generated_total = 0;
  std::uint64_t accepted_total = 0;
  std::uint64_t sent_total = 0;
  std::uint64_t sent_word_total = 0;
  std::uint64_t busy_total = 0;
  std::uint64_t full_total = 0;
  std::uint64_t spacing_total = 0;
  std::uint64_t queue_total = 0;
  std::uint64_t ring_total = 0;
  std::uint64_t output_total = 0;

  bool in_measure(std::uint64_t time) const {
    return time >= measure_lo && time < measure_hi;
  }

  int lane_of_channel(int channel) const {
    return channel / cfg.channels_per_lane;
  }

  int local_channel_of(int channel) const {
    return channel % cfg.channels_per_lane;
  }

  std::uint64_t sample0_ts_for(std::uint64_t trigger_ts) const {
    if (trigger_ts >= static_cast<std::uint64_t>(cfg.pretrigger_samples)) {
      return trigger_ts - static_cast<std::uint64_t>(cfg.pretrigger_samples);
    }
    return 0;
  }

  int blocks_for_samples(std::uint64_t samples) const {
    if (samples == 0ULL) {
      return 0;
    }
    return static_cast<int>((samples + 31ULL) / 32ULL);
  }

  int record_words_for_samples(std::uint64_t samples) const {
    return 8 + blocks_for_samples(samples) * 7;
  }

  std::uint64_t serializer_cycles_for_samples(std::uint64_t samples) const {
    return static_cast<std::uint64_t>(8 + blocks_for_samples(samples) * 40);
  }

  void push_completed_record(int channel, int words) {
    ChannelState &state = channels[static_cast<std::size_t>(channel)];
    state.completed_record_words.push_back(words);
    state.completed_words += words;
  }

  std::uint64_t next_arrival_delta() {
    if (p <= 0.0) {
      return std::numeric_limits<std::uint64_t>::max();
    }
    return geometric(rng) + 1ULL;
  }

  void push_event(std::uint64_t time, EventKind kind, int channel) {
    events.push(Event{time, kind, event_seq++, channel});
  }

  void schedule_initial_arrivals() {
    if (p <= 0.0) {
      return;
    }
    for (int channel = 0; channel < cfg.channels; ++channel) {
      const std::uint64_t dt = next_arrival_delta();
      if (dt == std::numeric_limits<std::uint64_t>::max()) {
        continue;
      }
      push_event(cfg.reset_cycles + dt, EventKind::Arrival, channel);
    }
  }

  int visible_words(int channel, std::uint64_t time) const {
    const ChannelState &state = channels[static_cast<std::size_t>(channel)];
    int words = state.completed_words;
    const LaneState &lane = lanes[static_cast<std::size_t>(lane_of_channel(channel))];
    if (lane.current_service && lane.current_service->channel == channel && time >= lane.current_service->start) {
      const std::uint64_t elapsed = time - lane.current_service->start;
      const int drained = static_cast<int>(std::min<std::uint64_t>(elapsed, static_cast<std::uint64_t>(lane.current_service->words - 1)));
      words = std::max(0, words - drained);
    }
    return words;
  }

  bool ready(int channel, std::uint64_t time) const {
    return visible_words(channel, time) > cfg.prog_empty_thresh;
  }

  bool prog_full(int channel, std::uint64_t time) const {
    return visible_words(channel, time) >= cfg.prog_full_thresh;
  }

  void maybe_start_serializer(int channel, std::uint64_t time) {
    ChannelState &state = channels[static_cast<std::size_t>(channel)];
    if (state.serializer_active || state.queue.empty()) {
      return;
    }
    if (state.queue.front().maturity_time > time) {
      return;
    }
    const PendingFrame frame = state.queue.front();
    state.queue.pop_front();
    const std::uint64_t frame_samples = frame.end_ts >= frame.sample0_ts ? frame.end_ts - frame.sample0_ts + 1ULL : 0ULL;
    state.serializer_active = true;
    state.active_sample0_ts = frame.sample0_ts;
    state.active_end_ts = frame.end_ts;
    state.active_record_words = cfg.architecture == "coalesced" ? record_words_for_samples(frame_samples) : cfg.record_words;
    state.serializer_end =
        time + (cfg.architecture == "coalesced" ? serializer_cycles_for_samples(frame_samples)
                                                 : static_cast<std::uint64_t>(cfg.serializer_cycles));
    push_event(state.serializer_end, EventKind::SerializerEnd, channel);
  }

  void maybe_schedule_service(int lane_idx, std::uint64_t now) {
    LaneState &lane = lanes[static_cast<std::size_t>(lane_idx)];
    if (lane.current_service) {
      return;
    }

    int chosen = -1;
    int empty_steps = 0;
    for (int offs = 0; offs < cfg.channels_per_lane; ++offs) {
      const int local = (lane.rr_sel + offs) % cfg.channels_per_lane;
      const int channel = lane.channel_base + local;
      if (ready(channel, now)) {
        chosen = channel;
        empty_steps = offs;
        break;
      }
    }
    if (chosen < 0) {
      return;
    }

    const ChannelState &state = channels[static_cast<std::size_t>(chosen)];
    const int service_words = state.completed_record_words.empty() ? cfg.record_words : state.completed_record_words.front();
    const std::uint64_t start = now + static_cast<std::uint64_t>(empty_steps + 1);
    const std::uint64_t end = start + static_cast<std::uint64_t>(service_words);
    lane.current_service = Service{chosen, service_words, start, end};
    push_event(end, EventKind::ServiceEnd, chosen);
  }

  void handle_arrival(const Event &event) {
    if (cfg.architecture == "legacy") {
      handle_legacy_arrival(event);
      return;
    }
    if (cfg.architecture == "coalesced") {
      handle_coalesced_arrival(event);
      return;
    }

    ChannelState &state = channels[static_cast<std::size_t>(event.channel)];
    if (p > 0.0) {
      const std::uint64_t dt = next_arrival_delta();
      if (dt != std::numeric_limits<std::uint64_t>::max() && event.time + dt <= total_cycles) {
        push_event(event.time + dt, EventKind::Arrival, event.channel);
      }
    }

    if (in_measure(event.time)) {
      ++generated_total;
    }

    const bool spacing_ok = (!state.last_trigger_valid) ||
                            (event.time >= state.last_trigger_ts + static_cast<std::uint64_t>(min_trigger_spacing));
    const bool queue_space_ok = static_cast<int>(state.queue.size()) < cfg.queue_depth;

    bool oldest_valid = false;
    std::uint64_t oldest_sample0_ts = 0;
    if (state.serializer_active) {
      oldest_valid = true;
      oldest_sample0_ts = state.active_sample0_ts;
    } else if (!state.queue.empty()) {
      oldest_valid = true;
      oldest_sample0_ts = state.queue.front().sample0_ts;
    }

    const bool ring_safe_ok =
        (!oldest_valid) || (event.time - oldest_sample0_ts <= static_cast<std::uint64_t>(ring_safe_margin));
    const bool output_ok = !prog_full(event.channel, event.time);
    const bool can_accept = spacing_ok && queue_space_ok && ring_safe_ok && output_ok;

    if (can_accept) {
      const std::uint64_t sample0_ts = sample0_ts_for(event.time);
      const std::uint64_t end_ts = sample0_ts + static_cast<std::uint64_t>(cfg.frame_samples - 1);
      const std::uint64_t maturity_time = end_ts;
      state.queue.push_back(PendingFrame{sample0_ts, end_ts, maturity_time});
      state.last_trigger_valid = true;
      state.last_trigger_ts = event.time;
      push_event(maturity_time, EventKind::Maturity, event.channel);
      if (in_measure(event.time)) {
        ++accepted_total;
      }
      return;
    }

    if (!output_ok) {
      if (in_measure(event.time)) {
        ++full_total;
        ++output_total;
      }
    } else if (!spacing_ok) {
      if (in_measure(event.time)) {
        ++busy_total;
        ++spacing_total;
      }
    } else if (!queue_space_ok) {
      if (in_measure(event.time)) {
        ++busy_total;
        ++queue_total;
      }
    } else if (!ring_safe_ok) {
      if (in_measure(event.time)) {
        ++busy_total;
        ++ring_total;
      }
    } else if (in_measure(event.time)) {
      ++busy_total;
    }
  }

  void handle_maturity(const Event &event) {
    if (cfg.architecture != "ring" && cfg.architecture != "coalesced") {
      return;
    }
    maybe_start_serializer(event.channel, event.time);
  }

  void handle_serializer_end(const Event &event) {
    if (cfg.architecture != "ring" && cfg.architecture != "coalesced") {
      return;
    }
    ChannelState &state = channels[static_cast<std::size_t>(event.channel)];
    if (!state.serializer_active || state.serializer_end != event.time) {
      return;
    }
    state.serializer_active = false;
    push_completed_record(event.channel, state.active_record_words);
    state.active_sample0_ts = 0;
    state.active_end_ts = 0;
    state.active_record_words = 0;
    maybe_start_serializer(event.channel, event.time);
    maybe_schedule_service(lane_of_channel(event.channel), event.time);
  }

  void handle_service_end(const Event &event) {
    LaneState &lane = lanes[static_cast<std::size_t>(lane_of_channel(event.channel))];
    if (!lane.current_service || lane.current_service->channel != event.channel || lane.current_service->end != event.time) {
      return;
    }

    ChannelState &state = channels[static_cast<std::size_t>(event.channel)];
    if (!state.completed_record_words.empty()) {
      state.completed_words = std::max(0, state.completed_words - state.completed_record_words.front());
      state.completed_record_words.pop_front();
    }
    if (in_measure(event.time)) {
      ++sent_total;
      sent_word_total += static_cast<std::uint64_t>(lane.current_service->words);
    }
    lane.rr_sel = (local_channel_of(event.channel) + 1) % cfg.channels_per_lane;
    lane.current_service.reset();
    maybe_schedule_service(lane_of_channel(event.channel), event.time + 1);
  }

  void handle_legacy_arrival(const Event &event) {
    ChannelState &state = channels[static_cast<std::size_t>(event.channel)];
    if (p > 0.0) {
      const std::uint64_t dt = next_arrival_delta();
      if (dt != std::numeric_limits<std::uint64_t>::max() && event.time + dt <= total_cycles) {
        push_event(event.time + dt, EventKind::Arrival, event.channel);
      }
    }

    if (in_measure(event.time)) {
      ++generated_total;
    }

    const bool busy = event.time < state.busy_until;
    const bool output_ok = !prog_full(event.channel, event.time);

    if (busy) {
      if (in_measure(event.time)) {
        ++busy_total;
        ++spacing_total;
      }
      return;
    }

    if (!output_ok) {
      if (in_measure(event.time)) {
        ++full_total;
        ++output_total;
      }
      return;
    }

    state.busy_until = event.time + static_cast<std::uint64_t>(cfg.builder_busy_cycles);
    push_event(state.busy_until, EventKind::LegacyRecordReady, event.channel);
    if (in_measure(event.time)) {
      ++accepted_total;
    }
  }

  void handle_legacy_record_ready(const Event &event) {
    if (cfg.architecture != "legacy") {
      return;
    }
    ChannelState &state = channels[static_cast<std::size_t>(event.channel)];
    if (event.time != state.busy_until) {
      return;
    }
    push_completed_record(event.channel, cfg.record_words);
    maybe_schedule_service(lane_of_channel(event.channel), event.time);
  }

  void handle_coalesced_arrival(const Event &event) {
    ChannelState &state = channels[static_cast<std::size_t>(event.channel)];
    if (p > 0.0) {
      const std::uint64_t dt = next_arrival_delta();
      if (dt != std::numeric_limits<std::uint64_t>::max() && event.time + dt <= total_cycles) {
        push_event(event.time + dt, EventKind::Arrival, event.channel);
      }
    }

    if (in_measure(event.time)) {
      ++generated_total;
    }

    const std::uint64_t sample0_ts = sample0_ts_for(event.time);
    const std::uint64_t window_end_ts = sample0_ts + static_cast<std::uint64_t>(cfg.frame_samples - 1);

    // Coalesced mode keeps trigger acceptance separate from output intervals:
    // overlapping trigger windows become metadata on one non-overlapping
    // waveform interval, or clip the next interval start to the already-covered
    // sample range.
    bool oldest_valid = false;
    std::uint64_t oldest_sample0_ts = 0;
    if (state.serializer_active) {
      oldest_valid = true;
      oldest_sample0_ts = state.active_sample0_ts;
    } else if (!state.queue.empty()) {
      oldest_valid = true;
      oldest_sample0_ts = state.queue.front().sample0_ts;
    }

    const bool ring_safe_ok =
        (!oldest_valid) || (event.time - oldest_sample0_ts <= static_cast<std::uint64_t>(ring_safe_margin));
    const bool output_ok = !prog_full(event.channel, event.time);

    const bool already_covered = state.coverage_valid && window_end_ts <= state.coverage_end_ts;
    const bool merge_tail = !state.queue.empty() && sample0_ts <= state.queue.back().end_ts + 1ULL;
    const bool needs_new_interval = !already_covered && !merge_tail;
    const bool queue_space_ok = !needs_new_interval || static_cast<int>(state.queue.size()) < cfg.queue_depth;
    const bool can_accept = output_ok && ring_safe_ok && queue_space_ok;

    if (!can_accept) {
      if (!output_ok) {
        if (in_measure(event.time)) {
          ++full_total;
          ++output_total;
        }
      } else if (!queue_space_ok) {
        if (in_measure(event.time)) {
          ++busy_total;
          ++queue_total;
        }
      } else if (!ring_safe_ok) {
        if (in_measure(event.time)) {
          ++busy_total;
          ++ring_total;
        }
      } else if (in_measure(event.time)) {
        ++busy_total;
      }
      return;
    }

    if (already_covered) {
      if (in_measure(event.time)) {
        ++accepted_total;
      }
      return;
    }

    if (merge_tail) {
      PendingFrame &tail = state.queue.back();
      if (window_end_ts > tail.end_ts) {
        tail.end_ts = window_end_ts;
        tail.maturity_time = window_end_ts;
        push_event(tail.maturity_time, EventKind::Maturity, event.channel);
      }
      state.coverage_end_ts = std::max(state.coverage_end_ts, window_end_ts);
      if (in_measure(event.time)) {
        ++accepted_total;
      }
      return;
    }

    const std::uint64_t interval_start =
        state.coverage_valid && sample0_ts <= state.coverage_end_ts ? state.coverage_end_ts + 1ULL : sample0_ts;
    state.queue.push_back(PendingFrame{interval_start, window_end_ts, window_end_ts});
    state.coverage_valid = true;
    state.coverage_end_ts = window_end_ts;
    push_event(window_end_ts, EventKind::Maturity, event.channel);
    if (in_measure(event.time)) {
      ++accepted_total;
    }
  }
};

std::vector<SummaryRow> summarise(const std::vector<RunStats> &raw_rows) {
  std::vector<int> rates;
  for (const auto &row : raw_rows) {
    rates.push_back(row.rate_hz_per_channel);
  }
  std::sort(rates.begin(), rates.end());
  rates.erase(std::unique(rates.begin(), rates.end()), rates.end());

  std::vector<SummaryRow> out;
  out.reserve(rates.size());

  for (int rate : rates) {
    std::vector<double> generated;
    std::vector<double> accepted;
    std::vector<double> sent;
    std::vector<double> sent_words;
    std::vector<double> busy;
    std::vector<double> full;
    std::vector<double> spacing;
    std::vector<double> queue;
    std::vector<double> ring;
    std::vector<double> output;
    std::vector<double> dead;

    for (const auto &row : raw_rows) {
      if (row.rate_hz_per_channel != rate) {
        continue;
      }
      generated.push_back(static_cast<double>(row.generated_total));
      accepted.push_back(static_cast<double>(row.accepted_total));
      sent.push_back(static_cast<double>(row.sent_total));
      sent_words.push_back(static_cast<double>(row.sent_word_total));
      busy.push_back(static_cast<double>(row.busy_counter_total));
      full.push_back(static_cast<double>(row.full_counter_total));
      spacing.push_back(static_cast<double>(row.spacing_counter_total));
      queue.push_back(static_cast<double>(row.queue_counter_total));
      ring.push_back(static_cast<double>(row.ring_counter_total));
      output.push_back(static_cast<double>(row.output_counter_total));
      dead.push_back(row.dead_fraction);
    }

    SummaryRow row;
    row.rate_hz_per_channel = rate;
    row.repeats = static_cast<int>(generated.size());
    row.generated_total_mean = mean(generated);
    row.generated_total_std = stddev(generated);
    row.accepted_total_mean = mean(accepted);
    row.accepted_total_std = stddev(accepted);
    row.sent_total_mean = mean(sent);
    row.sent_total_std = stddev(sent);
    row.sent_word_total_mean = mean(sent_words);
    row.sent_word_total_std = stddev(sent_words);
    row.busy_counter_total_mean = mean(busy);
    row.busy_counter_total_std = stddev(busy);
    row.full_counter_total_mean = mean(full);
    row.full_counter_total_std = stddev(full);
    row.spacing_counter_total_mean = mean(spacing);
    row.spacing_counter_total_std = stddev(spacing);
    row.queue_counter_total_mean = mean(queue);
    row.queue_counter_total_std = stddev(queue);
    row.ring_counter_total_mean = mean(ring);
    row.ring_counter_total_std = stddev(ring);
    row.output_counter_total_mean = mean(output);
    row.output_counter_total_std = stddev(output);
    row.dead_fraction_mean = mean(dead);
    row.dead_fraction_std = stddev(dead);
    out.push_back(row);
  }
  return out;
}

void write_raw_csv(const std::string &path, const std::vector<RunStats> &rows) {
  std::ofstream out(path);
  if (!out) {
    throw std::runtime_error("failed to open raw CSV for writing: " + path);
  }
  out << "rate_hz_per_channel,repeat_index,signal_delay_steps,generated_total,accepted_total,sent_total,sent_word_total,"
         "busy_counter_total,full_counter_total,spacing_counter_total,queue_counter_total,ring_counter_total,"
         "output_counter_total,dead_ppm,dead_fraction\n";
  out << std::fixed << std::setprecision(9);
  for (const auto &row : rows) {
    out << row.rate_hz_per_channel << ','
        << row.repeat_index << ','
        << row.signal_delay_steps << ','
        << row.generated_total << ','
        << row.accepted_total << ','
        << row.sent_total << ','
        << row.sent_word_total << ','
        << row.busy_counter_total << ','
        << row.full_counter_total << ','
        << row.spacing_counter_total << ','
        << row.queue_counter_total << ','
        << row.ring_counter_total << ','
        << row.output_counter_total << ','
        << row.dead_ppm << ','
        << row.dead_fraction << '\n';
  }
}

void write_summary_csv(const std::string &path, const std::vector<SummaryRow> &rows) {
  std::ofstream out(path);
  if (!out) {
    throw std::runtime_error("failed to open summary CSV for writing: " + path);
  }
  out << "rate_hz_per_channel,repeats,"
         "generated_total_mean,generated_total_std,"
         "accepted_total_mean,accepted_total_std,"
         "sent_total_mean,sent_total_std,"
         "sent_word_total_mean,sent_word_total_std,"
         "busy_counter_total_mean,busy_counter_total_std,"
         "full_counter_total_mean,full_counter_total_std,"
         "spacing_counter_total_mean,spacing_counter_total_std,"
         "queue_counter_total_mean,queue_counter_total_std,"
         "ring_counter_total_mean,ring_counter_total_std,"
         "output_counter_total_mean,output_counter_total_std,"
         "dead_fraction_mean,dead_fraction_std\n";
  out << std::fixed << std::setprecision(9);
  for (const auto &row : rows) {
    out << row.rate_hz_per_channel << ','
        << row.repeats << ','
        << row.generated_total_mean << ','
        << row.generated_total_std << ','
        << row.accepted_total_mean << ','
        << row.accepted_total_std << ','
        << row.sent_total_mean << ','
        << row.sent_total_std << ','
        << row.sent_word_total_mean << ','
        << row.sent_word_total_std << ','
        << row.busy_counter_total_mean << ','
        << row.busy_counter_total_std << ','
        << row.full_counter_total_mean << ','
        << row.full_counter_total_std << ','
        << row.spacing_counter_total_mean << ','
        << row.spacing_counter_total_std << ','
        << row.queue_counter_total_mean << ','
        << row.queue_counter_total_std << ','
        << row.ring_counter_total_mean << ','
        << row.ring_counter_total_std << ','
        << row.output_counter_total_mean << ','
        << row.output_counter_total_std << ','
        << row.dead_fraction_mean << ','
        << row.dead_fraction_std << '\n';
  }
}

}  // namespace

int main(int argc, char **argv) {
  try {
    const Config cfg = parse_args(argc, argv);
    const std::vector<int> rates = sweep_rates(cfg);

    std::vector<RunStats> raw_rows;
    raw_rows.reserve(static_cast<std::size_t>(rates.size() * cfg.repeats));

    for (int rate : rates) {
      for (int repeat_idx = 0; repeat_idx < cfg.repeats; ++repeat_idx) {
        Simulator simulator(cfg, rate, repeat_idx);
        raw_rows.push_back(simulator.run());
      }
    }

    const std::vector<SummaryRow> summary_rows = summarise(raw_rows);

    std::cout << "rate_hz/ch repeats dead_frac_mean dead_frac_std busy_mean full_mean spacing_mean ring_mean output_mean\n";
    std::cout << std::fixed << std::setprecision(6);
    for (const auto &row : summary_rows) {
      std::cout << std::setw(10) << row.rate_hz_per_channel << ' '
                << std::setw(7) << row.repeats << ' '
                << std::setw(14) << row.dead_fraction_mean << ' '
                << std::setw(13) << row.dead_fraction_std << ' '
                << std::setw(9) << row.busy_counter_total_mean << ' '
                << std::setw(9) << row.full_counter_total_mean << ' '
                << std::setw(12) << row.spacing_counter_total_mean << ' '
                << std::setw(9) << row.ring_counter_total_mean << ' '
                << std::setw(11) << row.output_counter_total_mean << '\n';
    }

    if (!cfg.raw_csv_out.empty()) {
      write_raw_csv(cfg.raw_csv_out, raw_rows);
    }
    if (!cfg.csv_out.empty()) {
      write_summary_csv(cfg.csv_out, summary_rows);
    }
  } catch (const std::exception &ex) {
    std::cerr << "ERROR: " << ex.what() << '\n';
    return 1;
  }

  return 0;
}

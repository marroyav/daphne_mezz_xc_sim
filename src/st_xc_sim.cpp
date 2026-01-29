#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr int kTaps = 32;

// Default template from ip_repo/daphne3_ip/rtl/selftrig/eia_selftrig/st_xc.vhd
const int kTemplate[kTaps] = {
    1, 0, 0, 0, 0, 0, -1, -1,
    -1, -1, -1, -2, -2, -3, -4, -4,
    -5, -5, -6, -7, -6, -7, -7, -7,
    -7, -6, -5, -4, -3, -2, -1, 0
};

struct Options {
    std::string input_path;
    std::string out_prefix = "data/output/analysis/out";
    std::string template_path;
    int64_t threshold = 0;
    bool unsigned14 = false;
    bool no_center = false;
    bool input_bin16 = false;
    int baseline_sub = 0;
    bool auto_baseline = false;
    bool xcorr_abs = false;
    bool xcorr_negate = false;
    int holdoff = 0;
    int frame_len = 1024;
    int pretrigger = 64;
    int data_delay = 256;
    int reset_samples = 0;
};

struct SampleOut {
    int64_t xcorr_raw = 0;
    int64_t xcorr_proc = 0;
    int raw_delayed = 0;
    int trigger = 0;
    int frame_start = 0;
    int frame_active = 0;
    int frame_index = 0;
    int frame_id = 0;
    int frame_trigger = 0;
};

void PrintUsage(const char* prog) {
    std::cerr
        << "Usage: " << prog << " --input <waveform> [options]\n"
        << "Options:\n"
        << "  --out-prefix <prefix>   Output prefix\n"
        << "  --template <file.txt>   Template coefficients, one per line\n"
        << "  --threshold <int>       Trigger threshold (signed)\n"
        << "  --unsigned14            Treat input as unsigned 14-bit (0..16383)\n"
        << "  --unsigned14-no-center  Do not subtract 8192 when using --unsigned14\n"
        << "  --input-bin16           Read input as 16-bit little-endian samples\n"
        << "  --baseline-sub <int>    Subtract baseline before filtering\n"
        << "  --auto-baseline         Compute mean of input and use as baseline-sub\n"
        << "  --xcorr-abs             Use absolute value of xcorr for trigger/output\n"
        << "  --xcorr-negate          Negate xcorr for trigger/output\n"
        << "  --holdoff <N>           Suppress triggers for N samples after trigger\n"
        << "  --frame-len <N>         Frame length in samples (default: 1024)\n"
        << "  --pretrigger <N>        Pretrigger samples (default: 64)\n"
        << "  --data-delay <N>        Data delay in samples (default: 256)\n"
        << "  --reset-samples <N>     Assert reset for first N samples\n";
}

bool ParseArgs(int argc, char** argv, Options& opt) {
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--input" && i + 1 < argc) opt.input_path = argv[++i];
        else if (arg == "--out-prefix" && i + 1 < argc) opt.out_prefix = argv[++i];
        else if (arg == "--template" && i + 1 < argc) opt.template_path = argv[++i];
        else if (arg == "--threshold" && i + 1 < argc) opt.threshold = std::strtoll(argv[++i], nullptr, 0);
        else if (arg == "--unsigned14") opt.unsigned14 = true;
        else if (arg == "--unsigned14-no-center") opt.no_center = true;
        else if (arg == "--input-bin16") opt.input_bin16 = true;
        else if (arg == "--baseline-sub" && i + 1 < argc) opt.baseline_sub = std::atoi(argv[++i]);
        else if (arg == "--auto-baseline") opt.auto_baseline = true;
        else if (arg == "--xcorr-abs") opt.xcorr_abs = true;
        else if (arg == "--xcorr-negate") opt.xcorr_negate = true;
        else if (arg == "--holdoff" && i + 1 < argc) opt.holdoff = std::atoi(argv[++i]);
        else if (arg == "--frame-len" && i + 1 < argc) opt.frame_len = std::atoi(argv[++i]);
        else if (arg == "--pretrigger" && i + 1 < argc) opt.pretrigger = std::atoi(argv[++i]);
        else if (arg == "--data-delay" && i + 1 < argc) opt.data_delay = std::atoi(argv[++i]);
        else if (arg == "--reset-samples" && i + 1 < argc) opt.reset_samples = std::atoi(argv[++i]);
        else return false;
    }
    return !opt.input_path.empty();
}

int ClampSigned14(int64_t v) {
    if (v > 8191) return 8191;
    if (v < -8192) return -8192;
    return static_cast<int>(v);
}

int ClampUnsigned14(int64_t v) {
    if (v > 16383) return 16383;
    if (v < 0) return 0;
    return static_cast<int>(v);
}

bool LoadTemplate(const std::string& path, std::vector<int>& tmpl) {
    std::ifstream in(path);
    if (!in) return false;
    tmpl.clear();
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream iss(line);
        int v = 0;
        if (iss >> v) tmpl.push_back(v);
    }
    return !tmpl.empty();
}

std::vector<int> ReadSamples(const Options& opt) {
    std::vector<int> samples;
    std::ifstream in(opt.input_path, opt.input_bin16 ? std::ios::binary : std::ios::in);
    if (!in) return samples;

    if (opt.input_bin16) {
        while (true) {
            uint16_t raw_u16 = 0;
            in.read(reinterpret_cast<char*>(&raw_u16), sizeof(raw_u16));
            if (!in) break;
            int sample = 0;
            if (opt.unsigned14) {
                sample = ClampUnsigned14(static_cast<int64_t>(raw_u16));
                if (!opt.no_center) sample -= 8192;
            } else {
                int16_t v = static_cast<int16_t>(raw_u16);
                sample = ClampSigned14(v);
            }
            samples.push_back(sample);
        }
        return samples;
    }

    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream iss(line);
        int64_t v = 0;
        if (!(iss >> v)) continue;
        int sample = opt.unsigned14 ? ClampUnsigned14(v) : ClampSigned14(v);
        if (opt.unsigned14 && !opt.no_center) sample -= 8192;
        samples.push_back(sample);
    }
    return samples;
}

int ComputeBaseline(const std::vector<int>& samples) {
    if (samples.empty()) return 0;
    int64_t sum = 0;
    for (int v : samples) sum += v;
    return static_cast<int>(sum / static_cast<int64_t>(samples.size()));
}

class XCorrSim {
public:
    XCorrSim(const Options& opt, const std::vector<int>& tmpl)
        : opt_(opt), tmpl_(tmpl),
          r_(kTaps + 1, 0), d0_(kTaps, 0), d1_(kTaps, 0),
          raw_delay_(std::max(0, opt.data_delay) + 1, 0) {}

    SampleOut Step(int sample, bool reset) {
        SampleOut out;
        out.xcorr_raw = xcorr_;
        out.xcorr_proc = ApplyXCorrOps(xcorr_);

        out.trigger = ShouldTrigger(out.xcorr_proc);
        UpdateFrame(out.trigger, reset, out);

        out.raw_delayed = raw_delay_[raw_delay_pos_];
        raw_delay_[raw_delay_pos_] = sample;
        raw_delay_pos_ = (raw_delay_pos_ + 1) % raw_delay_.size();

        if (reset) {
            ResetState();
            return out;
        }

        UpdateFIR(sample);
        UpdateXCorrPipeline();

        return out;
    }

private:
    int64_t ApplyXCorrOps(int64_t v) const {
        int64_t out = v;
        if (opt_.xcorr_negate) out = -out;
        if (opt_.xcorr_abs) out = std::llabs(out);
        return out;
    }

    int ShouldTrigger(int64_t xcorr_proc) {
        if (holdoff_ > 0) {
            --holdoff_;
            return 0;
        }
        int64_t x0 = xcorr_proc;
        int64_t x1 = ApplyXCorrOps(xcorr_reg0_);
        int64_t x2 = ApplyXCorrOps(xcorr_reg1_);
        if (x0 > opt_.threshold && x1 > opt_.threshold && x2 <= opt_.threshold) {
            holdoff_ = opt_.holdoff;
            return 1;
        }
        return 0;
    }

    void UpdateFrame(int trigger, bool reset, SampleOut& out) {
        if (reset) {
            frame_active_ = false;
            frame_index_ = 0;
            frame_id_ = 0;
            out.frame_active = 0;
            out.frame_index = 0;
            out.frame_id = 0;
            out.frame_start = 0;
            out.frame_trigger = 0;
            return;
        }

        out.frame_start = 0;
        out.frame_trigger = 0;

        if (!frame_active_ && trigger) {
            frame_active_ = true;
            frame_index_ = 0;
            ++frame_id_;
            out.frame_start = 1;
        } else if (frame_active_) {
            if (frame_index_ >= opt_.frame_len - 1) {
                frame_active_ = false;
                frame_index_ = 0;
            } else {
                ++frame_index_;
            }
        }

        if (frame_active_ && frame_index_ == opt_.pretrigger) out.frame_trigger = 1;

        out.frame_active = frame_active_ ? 1 : 0;
        out.frame_index = frame_index_;
        out.frame_id = frame_id_;
    }

    void UpdateFIR(int sample) {
        std::vector<int64_t> new_r(kTaps + 1, 0);
        std::vector<int64_t> new_d0(kTaps, 0);
        std::vector<int64_t> new_d1(kTaps, 0);
        new_r[kTaps] = 0;

        for (int i = 0; i < kTaps; ++i) {
            int64_t acc_in = r_[i + 1];
            int64_t in_val = (tmpl_[i] == 0) ? acc_in : (static_cast<int64_t>(tmpl_[i]) * sample + acc_in);
            new_d0[i] = in_val;
            new_d1[i] = d0_[i];
            new_r[i] = d1_[i];
        }

        r_.swap(new_r);
        d0_.swap(new_d0);
        d1_.swap(new_d1);
    }

    void UpdateXCorrPipeline() {
        int64_t next_s_r = r_[0];
        int64_t next_xcorr = s_r_st_xc_;
        int64_t next_xcorr_reg0 = xcorr_;
        int64_t next_xcorr_reg1 = xcorr_reg0_;

        s_r_st_xc_ = next_s_r;
        xcorr_ = next_xcorr;
        xcorr_reg0_ = next_xcorr_reg0;
        xcorr_reg1_ = next_xcorr_reg1;
    }

    void ResetState() {
        std::fill(r_.begin(), r_.end(), 0);
        std::fill(d0_.begin(), d0_.end(), 0);
        std::fill(d1_.begin(), d1_.end(), 0);
        s_r_st_xc_ = 0;
        xcorr_ = 0;
        xcorr_reg0_ = 0;
        xcorr_reg1_ = 0;
        holdoff_ = 0;
        std::fill(raw_delay_.begin(), raw_delay_.end(), 0);
        raw_delay_pos_ = 0;
    }

    const Options& opt_;
    const std::vector<int>& tmpl_;

    std::vector<int64_t> r_;
    std::vector<int64_t> d0_;
    std::vector<int64_t> d1_;

    int64_t s_r_st_xc_ = 0;
    int64_t xcorr_ = 0;
    int64_t xcorr_reg0_ = 0;
    int64_t xcorr_reg1_ = 0;

    int holdoff_ = 0;
    bool frame_active_ = false;
    int frame_index_ = 0;
    int frame_id_ = 0;

    std::vector<int> raw_delay_;
    size_t raw_delay_pos_ = 0;
};

} // namespace

int main(int argc, char** argv) {
    Options opt;
    if (!ParseArgs(argc, argv, opt)) {
        PrintUsage(argv[0]);
        return 1;
    }

    std::vector<int> tmpl;
    if (!opt.template_path.empty()) {
        if (!LoadTemplate(opt.template_path, tmpl)) {
            std::cerr << "Failed to read template file: " << opt.template_path << "\n";
            return 1;
        }
        if (tmpl.size() != kTaps) {
            std::cerr << "Template must have exactly " << kTaps << " coefficients. Got " << tmpl.size() << "\n";
            return 1;
        }
    } else {
        tmpl.assign(kTemplate, kTemplate + kTaps);
    }

    std::vector<int> samples = ReadSamples(opt);
    if (samples.empty()) {
        std::cerr << "Failed to open input file: " << opt.input_path << "\n";
        return 1;
    }

    if (opt.auto_baseline) opt.baseline_sub = ComputeBaseline(samples);

    const std::string csv_path = opt.out_prefix + ".csv";
    const std::string raw_path = opt.out_prefix + "_raw.txt";
    const std::string xcorr_path = opt.out_prefix + "_xcorr.txt";
    const std::string trig_path = opt.out_prefix + "_trigger.txt";

    std::ofstream csv(csv_path);
    std::ofstream raw_out(raw_path);
    std::ofstream xcorr_out(xcorr_path);
    std::ofstream trig_out(trig_path);
    if (!csv || !raw_out || !xcorr_out || !trig_out) {
        std::cerr << "Failed to open output files with prefix: " << opt.out_prefix << "\n";
        return 1;
    }

    csv << "index,raw,raw_delayed,xcorr,xcorr_proc,trigger,frame_start,frame_active,frame_index,frame_id,frame_trigger\n";

    XCorrSim sim(opt, tmpl);
    int64_t index = 0;
    for (int v : samples) {
        int sample = v;
        if (opt.baseline_sub != 0) sample = ClampSigned14(static_cast<int64_t>(sample) - opt.baseline_sub);
        bool reset = index < opt.reset_samples;
        SampleOut out = sim.Step(sample, reset);

        csv << index << "," << sample << "," << out.raw_delayed << "," << out.xcorr_raw << "," << out.xcorr_proc
            << "," << out.trigger << "," << out.frame_start << "," << out.frame_active << "," << out.frame_index
            << "," << out.frame_id << "," << out.frame_trigger << "\n";
        raw_out << sample << "\n";
        xcorr_out << out.xcorr_proc << "\n";
        trig_out << out.trigger << "\n";
        ++index;
    }

    return 0;
}

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
    uint16_t ciemat_config = 0x36CD; // DEFAULT_st_config_command[15:2]
    int ciemat_delay = 176;
    bool ciemat_invert = false;
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
    int desc_valid = 0;
    int desc_time_peak = 0;
    int desc_time_over = 0;
    int desc_peak = 0;
    int desc_charge = 0;
    int desc_charge_simple = 0;
    int desc_peak_count = 0;
    int desc_time_start = 0;
    int desc_peak_current = 0;
    int desc_slope_current = 0;
    int desc_detection = 0;
    int desc_sending = 0;
    int desc_info_previous = 0;
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
        << "  --ciemat-config <hex>   14-bit CIEMAT config (default: 0x36CD)\n"
        << "  --ciemat-delay <N>      CIEMAT primitive input delay (default: 176)\n"
        << "  --ciemat-invert         Invert sample sign before CIEMAT primitives\n"
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
        else if (arg == "--ciemat-config" && i + 1 < argc) opt.ciemat_config = static_cast<uint16_t>(std::strtoul(argv[++i], nullptr, 0));
        else if (arg == "--ciemat-delay" && i + 1 < argc) opt.ciemat_delay = std::atoi(argv[++i]);
        else if (arg == "--ciemat-invert") opt.ciemat_invert = true;
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

int16_t WrapSigned14(int32_t v) {
    v &= 0x3FFF;
    if (v & 0x2000) v -= 0x4000;
    return static_cast<int16_t>(v);
}

int16_t WrapSigned15(int32_t v) {
    v &= 0x7FFF;
    if (v & 0x4000) v -= 0x8000;
    return static_cast<int16_t>(v);
}

uint16_t MaskUnsigned(int32_t v, int bits) {
    uint32_t mask = (1u << bits) - 1u;
    return static_cast<uint16_t>(v) & mask;
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

class CiematPeakDetector {
public:
    void Reset() {
        std::fill(delays_, delays_ + 20, 0);
        slope_current_ = 0;
        allow_peak_ = true;
        peak_current_ = false;
        detection_reg_ = false;
        reset_timer_ = 64;
        not_allow_trigger_ = true;
    }

    void SetConfig(uint16_t config10) {
        main_peak_ = (config10 & 0x1) != 0;
        allow_partial_ = (config10 & 0x2) != 0;
        slope_config_ = (config10 & 0x4) != 0;
        int s = static_cast<int>((config10 >> 3) & 0x7F);
        if (s & 0x40) s -= 0x80;
        slope_threshold_ = s;
    }

    void SetDetection(bool det) { detection_reg_ = det; }

    void Step(int16_t din, bool sending_data) {
        for (int i = 19; i > 0; --i) delays_[i] = delays_[i - 1];
        delays_[0] = din;

        int16_t slope_select = slope_config_ ? delays_[19] : delays_[15];
        int32_t slope_aux = static_cast<int32_t>(delays_[0]) - static_cast<int32_t>(slope_select);
        slope_current_ = WrapSigned14(slope_aux);

        int32_t slope_thresh_ext = slope_threshold_;
        if (slope_current_ <= slope_thresh_ext && allow_peak_) {
            peak_current_ = true;
        } else {
            peak_current_ = false;
        }

        if (allow_peak_) {
            if (slope_current_ <= slope_thresh_ext) {
                allow_peak_ = false;
            }
        } else {
            if (slope_current_ > (slope_thresh_ext + 5)) {
                allow_peak_ = true;
            }
        }

        if (reset_timer_ > 0) {
            --reset_timer_;
            not_allow_trigger_ = true;
        } else {
            not_allow_trigger_ = false;
        }

        self_trigger_ = (((peak_current_) && (!main_peak_)) ||
                         ((main_peak_) && (peak_current_) && (!detection_reg_)) ||
                         ((allow_partial_) && (detection_reg_) && (!sending_data))) &&
                        (!not_allow_trigger_);
    }

    bool peak_current() const { return peak_current_; }
    int16_t slope_current() const { return slope_current_; }
    bool self_trigger() const { return self_trigger_; }

private:
    int16_t delays_[20] = {0};
    int16_t slope_current_ = 0;
    bool allow_peak_ = true;
    bool peak_current_ = false;
    bool detection_reg_ = false;
    int reset_timer_ = 64;
    bool not_allow_trigger_ = true;
    bool main_peak_ = false;
    bool allow_partial_ = false;
    bool slope_config_ = false;
    int slope_threshold_ = -19;
    bool self_trigger_ = false;
};

class CiematLocalPrimitives {
public:
    void Reset() {
        state_ = State::No_Detection;
        time_peak_ = 0;
        time_over_ = 0;
        adc_peak_ = 0;
        adc_integral_ = 0;
        charge_simple_ = 0;
        num_peaks_ = 0;
        detection_time_ = kMaxDetectionTime;
        high_freq_noise_ = false;
        amplitude_current_ = 0;
        amplitude_reg1_ = 0;
        amplitude_reg2_ = 0;
        amplitude_reg3_ = 0;
        amplitude_reg4_ = 0;
    }

    void Step(int16_t din, bool self_trigger, bool peak_current) {
        amplitude_current_ = WrapSigned15(din);
        amplitude_reg1_ = amplitude_current_;
        amplitude_reg2_ = amplitude_reg1_;
        amplitude_reg3_ = amplitude_reg2_;
        amplitude_reg4_ = amplitude_reg3_;
        int amp_pos = std::max<int>(0, amplitude_current_);

        State next = state_;
        if (state_ == State::No_Detection) {
            next = self_trigger ? State::Detection : State::No_Detection;
        } else if (state_ == State::Detection) {
            if ((amplitude_current_ > 0) && (time_over_ > kMinTimeOver)) {
                next = State::Data;
            } else if (detection_time_ <= 0) {
                next = State::No_Detection;
            } else {
                next = State::Detection;
            }
        } else if (state_ == State::Data) {
            next = self_trigger ? State::Detection : State::No_Detection;
        }

        state_ = next;
        if (state_ == State::No_Detection) {
            time_peak_ = 0;
            time_over_ = 1;
            adc_peak_ = 0;
            adc_integral_ = 0;
            charge_simple_ = 0;
            num_peaks_ = 1;
            detection_time_ = kMaxDetectionTime;
        } else if (state_ == State::Detection) {
            time_over_ = static_cast<int>(MaskUnsigned(time_over_ + 1, 9));
            if (amplitude_current_ < 0) {
                adc_integral_ = static_cast<int>(MaskUnsigned(adc_integral_ - amplitude_current_, 23));
            }
            charge_simple_ = static_cast<int>(MaskUnsigned(charge_simple_ + amp_pos, 23));
            detection_time_ -= 1;
            int16_t amp_mag = static_cast<int16_t>(-amplitude_current_);
            if (adc_peak_ <= amp_mag) {
                time_peak_ = time_over_ & 0x1FF;
                adc_peak_ = amp_mag;
            }
            if (peak_current) {
                num_peaks_ = static_cast<int>(MaskUnsigned(num_peaks_ + 1, 4));
            }
        }

        if (state_ == State::Data && (time_over_ < kMinTimeOver)) {
            high_freq_noise_ = true;
        } else {
            high_freq_noise_ = false;
        }
    }

    bool data_available() const { return state_ == State::Data; }
    bool peak_detection() const { return state_ == State::Detection; }
    int time_peak() const { return time_peak_ & 0x1FF; }
    int time_over() const { return time_over_ & 0x1FF; }
    int adc_peak() const { return adc_peak_ & 0x3FFF; }
    int adc_integral() const { return adc_integral_ & 0x7FFFFF; }
    int charge_simple() const { return charge_simple_ & 0x7FFFFF; }
    int num_peaks() const { return num_peaks_ & 0xF; }
    bool high_freq_noise() const { return high_freq_noise_; }

private:
    enum class State { No_Detection, Detection, Data };
    static constexpr int kMinTimeOver = 20;
    static constexpr int kMaxDetectionTime = 2048;

    State state_ = State::No_Detection;
    int time_peak_ = 0;
    int time_over_ = 0;
    int adc_peak_ = 0;
    int adc_integral_ = 0;
    int charge_simple_ = 0;
    int num_peaks_ = 0;
    int detection_time_ = kMaxDetectionTime;
    bool high_freq_noise_ = false;
    int16_t amplitude_current_ = 0;
    int16_t amplitude_reg1_ = 0;
    int16_t amplitude_reg2_ = 0;
    int16_t amplitude_reg3_ = 0;
    int16_t amplitude_reg4_ = 0;
};

class CiematSim {
public:
    explicit CiematSim(const Options& opt)
        : opt_(opt), delay_(std::max(0, opt.ciemat_delay) + 1, 0) {
        SetConfig(opt.ciemat_config);
        Reset();
    }

    void Reset() {
        peak_detector_.Reset();
        local_primitives_.Reset();
        std::fill(delay_.begin(), delay_.end(), 0);
        delay_pos_ = 0;
        sending_state_ = SendingState::Not_Sending;
        data_sent_count_ = 0;
        info_previous_ = false;
        time_start_reg_ = 0;
        time_start_reg2_ = 0;
    }

    void SetConfig(uint16_t config14) {
        config14_ = config14 & 0x3FFF;
        uint16_t config10 = static_cast<uint16_t>((config14_ >> 4) & 0x3FF);
        peak_detector_.SetConfig(config10);
        allow_previous_info_ = (config10 & 0x2) != 0;
    }

    void Step(int16_t din, bool ext_trigger, bool match_with_frame, SampleOut& out) {
        int16_t delayed = delay_[delay_pos_];
        delay_[delay_pos_] = din;
        delay_pos_ = (delay_pos_ + 1) % delay_.size();

        bool sending_data = (sending_state_ == SendingState::Sending);
        bool ext_match = ext_trigger && (match_with_frame || sending_data);

        peak_detector_.Step(din, sending_data);

        local_primitives_.Step(delayed, ext_match, peak_detector_.peak_current());

        peak_detector_.SetDetection(local_primitives_.peak_detection());

        UpdateSending(ext_trigger, match_with_frame);
        UpdateInfoPrevious(local_primitives_.peak_detection());
        UpdateTimeStart(ext_match, local_primitives_.data_available());

        out.desc_valid = local_primitives_.data_available() ? 1 : 0;
        out.desc_time_peak = local_primitives_.time_peak();
        out.desc_time_over = local_primitives_.time_over();
        out.desc_peak = local_primitives_.adc_peak();
        out.desc_charge = local_primitives_.adc_integral();
        out.desc_charge_simple = local_primitives_.charge_simple();
        out.desc_peak_count = local_primitives_.num_peaks();
        out.desc_time_start = time_start_reg2_ & 0x3FF;
        out.desc_peak_current = peak_detector_.peak_current() ? 1 : 0;
        out.desc_slope_current = static_cast<int>(peak_detector_.slope_current());
        out.desc_detection = local_primitives_.peak_detection() ? 1 : 0;
        out.desc_sending = (sending_state_ == SendingState::Sending) ? 1 : 0;
        out.desc_info_previous = info_previous_ ? 1 : 0;
    }

private:
    enum class SendingState { Not_Sending, Sending };
    static constexpr int kFrameSize = 960;

    void UpdateSending(bool ext_trigger, bool match_with_frame) {
        SendingState next = sending_state_;
        if (sending_state_ == SendingState::Not_Sending) {
            next = (ext_trigger && match_with_frame) ? SendingState::Sending : SendingState::Not_Sending;
        } else {
            next = (data_sent_count_ >= kFrameSize) ? SendingState::Not_Sending : SendingState::Sending;
        }

        sending_state_ = next;
        if (sending_state_ == SendingState::Not_Sending) {
            data_sent_count_ = 0;
        } else {
            data_sent_count_ += 1;
        }
    }

    void UpdateInfoPrevious(bool detection) {
        if ((allow_previous_info_) && (sending_state_ == SendingState::Not_Sending) && detection && !info_previous_) {
            info_previous_ = true;
        } else if ((sending_state_ == SendingState::Not_Sending) && info_previous_) {
            info_previous_ = false;
        }
    }

    void UpdateTimeStart(bool ext_match, bool data_available) {
        int time_start_aux = data_sent_count_ + 64;
        if (ext_match) {
            time_start_reg_ = time_start_aux;
        } else if (data_available) {
            time_start_reg2_ = time_start_reg_;
        }
    }

    const Options& opt_;
    uint16_t config14_ = 0;
    bool allow_previous_info_ = false;
    CiematPeakDetector peak_detector_;
    CiematLocalPrimitives local_primitives_;
    std::vector<int16_t> delay_;
    size_t delay_pos_ = 0;
    SendingState sending_state_ = SendingState::Not_Sending;
    int data_sent_count_ = 0;
    bool info_previous_ = false;
    int time_start_reg_ = 0;
    int time_start_reg2_ = 0;
};

class XCorrSim {
public:
    XCorrSim(const Options& opt, const std::vector<int>& tmpl)
        : opt_(opt), tmpl_(tmpl),
          r_(kTaps + 1, 0), d0_(kTaps, 0), d1_(kTaps, 0),
          raw_delay_(std::max(0, opt.data_delay) + 1, 0),
          ciemat_(opt) {}

    SampleOut Step(int sample, bool reset) {
        SampleOut out;
        out.xcorr_raw = xcorr_;
        out.xcorr_proc = ApplyXCorrOps(xcorr_);

        out.trigger = ShouldTrigger(out.xcorr_proc);
        bool match_with_frame = !frame_active_;
        UpdateFrame(out.trigger, reset, out);

        int ciemat_sample = sample;
        if (opt_.ciemat_invert) ciemat_sample = -ciemat_sample;
        ciemat_sample = ClampSigned14(ciemat_sample);
        ciemat_.Step(static_cast<int16_t>(ciemat_sample), out.trigger != 0, match_with_frame, out);

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
        frame_active_ = false;
        frame_index_ = 0;
        frame_id_ = 0;
        ciemat_.Reset();
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

    CiematSim ciemat_;
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

    csv << "index,raw,raw_delayed,xcorr,xcorr_proc,trigger,frame_start,frame_active,frame_index,frame_id,frame_trigger,"
           "desc_valid,desc_time_peak,desc_time_over,desc_peak,desc_charge,desc_charge_simple,desc_peak_count,desc_time_start,"
           "desc_peak_current,desc_slope_current,desc_detection,desc_sending,desc_info_previous\n";

    XCorrSim sim(opt, tmpl);
    int64_t index = 0;
    for (int v : samples) {
        int sample = v;
        if (opt.baseline_sub != 0) sample = ClampSigned14(static_cast<int64_t>(sample) - opt.baseline_sub);
        bool reset = index < opt.reset_samples;
        SampleOut out = sim.Step(sample, reset);

        csv << index << "," << sample << "," << out.raw_delayed << "," << out.xcorr_raw << "," << out.xcorr_proc
            << "," << out.trigger << "," << out.frame_start << "," << out.frame_active << "," << out.frame_index
            << "," << out.frame_id << "," << out.frame_trigger
            << "," << out.desc_valid << "," << out.desc_time_peak << "," << out.desc_time_over
            << "," << out.desc_peak << "," << out.desc_charge << "," << out.desc_charge_simple << "," << out.desc_peak_count
            << "," << out.desc_time_start << "," << out.desc_peak_current << "," << out.desc_slope_current
            << "," << out.desc_detection << "," << out.desc_sending << "," << out.desc_info_previous << "\n";
        raw_out << sample << "\n";
        xcorr_out << out.xcorr_proc << "\n";
        trig_out << out.trigger << "\n";
        ++index;
    }

    return 0;
}

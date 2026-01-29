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
    std::string out_prefix = "out";
    std::string template_path;
    int64_t threshold = 0;
    bool unsigned14 = false;
    bool input_bin16 = false;
    int reset_samples = 0;
    bool enable = true;
};

void PrintUsage(const char* prog) {
    std::cerr
        << "Usage: " << prog << " --input <waveform> [options]\n"
        << "Options:\n"
        << "  --out-prefix <prefix>   Output prefix (default: out)\n"
        << "  --template <file.txt>   Template coefficients, one per line\n"
        << "  --threshold <int>       Trigger threshold (signed)\n"
        << "  --unsigned14            Treat input as unsigned 14-bit (0..16383)\n"
        << "  --input-bin16           Read input as 16-bit little-endian signed samples\n"
        << "  --reset-samples <N>     Assert reset for first N samples (default: 0)\n";
}

bool ParseArgs(int argc, char** argv, Options& opt) {
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--input" && i + 1 < argc) {
            opt.input_path = argv[++i];
        } else if (arg == "--out-prefix" && i + 1 < argc) {
            opt.out_prefix = argv[++i];
        } else if (arg == "--template" && i + 1 < argc) {
            opt.template_path = argv[++i];
        } else if (arg == "--threshold" && i + 1 < argc) {
            opt.threshold = std::strtoll(argv[++i], nullptr, 0);
        } else if (arg == "--unsigned14") {
            opt.unsigned14 = true;
        } else if (arg == "--input-bin16") {
            opt.input_bin16 = true;
        } else if (arg == "--reset-samples" && i + 1 < argc) {
            opt.reset_samples = std::atoi(argv[++i]);
        } else {
            return false;
        }
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
    if (!in) {
        return false;
    }
    tmpl.clear();
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        if (line[0] == '#') continue;
        std::istringstream iss(line);
        int v = 0;
        if (!(iss >> v)) continue;
        tmpl.push_back(v);
    }
    return !tmpl.empty();
}

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

    std::ifstream in;
    in.open(opt.input_path, opt.input_bin16 ? std::ios::binary : std::ios::in);
    if (!in) {
        std::cerr << "Failed to open input file: " << opt.input_path << "\n";
        return 1;
    }

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

    csv << "index,raw,xcorr,trigger\n";

    // Registers for per-tap 2-cycle pipeline (matching zero-coeff reg path).
    std::vector<int64_t> r(kTaps + 1, 0);
    std::vector<int64_t> d0(kTaps, 0);
    std::vector<int64_t> d1(kTaps, 0);

    // Output pipeline registers
    int64_t s_r_st_xc = 0;
    int64_t xcorr = 0;
    int64_t xcorr_reg0 = 0;
    int64_t xcorr_reg1 = 0;

    int64_t index = 0;
    auto step = [&](int sample, bool reset) {
        int trigger = 0;
        if (opt.enable && !reset) {
            if (xcorr > opt.threshold && xcorr_reg0 > opt.threshold && xcorr_reg1 <= opt.threshold) {
                trigger = 1;
            }
        }

        // Log current outputs (before updating registers)
        csv << index << "," << sample << "," << xcorr << "," << trigger << "\n";
        raw_out << sample << "\n";
        xcorr_out << xcorr << "\n";
        trig_out << trigger << "\n";

        if (reset) {
            std::fill(r.begin(), r.end(), 0);
            std::fill(d0.begin(), d0.end(), 0);
            std::fill(d1.begin(), d1.end(), 0);
            s_r_st_xc = 0;
            xcorr = 0;
            xcorr_reg0 = 0;
            xcorr_reg1 = 0;
            return;
        }

        // Update FIR transposed structure with 2-cycle pipeline per tap.
        std::vector<int64_t> new_r(kTaps + 1, 0);
        std::vector<int64_t> new_d0(kTaps, 0);
        std::vector<int64_t> new_d1(kTaps, 0);
        new_r[kTaps] = 0;

        for (int i = 0; i < kTaps; ++i) {
            int64_t acc_in = r[i + 1];
            int64_t in_val = (tmpl[i] == 0) ? acc_in : (static_cast<int64_t>(tmpl[i]) * sample + acc_in);

            new_d0[i] = in_val;
            new_d1[i] = d0[i];
            new_r[i] = d1[i];
        }

        r.swap(new_r);
        d0.swap(new_d0);
        d1.swap(new_d1);

        // Update xcorr pipeline registers (gated by enable)
        if (opt.enable) {
            int64_t next_s_r = r[0];
            int64_t next_xcorr = s_r_st_xc;
            int64_t next_xcorr_reg0 = xcorr;
            int64_t next_xcorr_reg1 = xcorr_reg0;

            s_r_st_xc = next_s_r;
            xcorr = next_xcorr;
            xcorr_reg0 = next_xcorr_reg0;
            xcorr_reg1 = next_xcorr_reg1;
        }
    };

    if (opt.input_bin16) {
        while (true) {
            int16_t v = 0;
            in.read(reinterpret_cast<char*>(&v), sizeof(v));
            if (!in) break;
            int sample = opt.unsigned14 ? ClampUnsigned14(static_cast<int64_t>(static_cast<uint16_t>(v)))
                                        : ClampSigned14(v);
            if (opt.unsigned14) sample -= 8192;

            bool reset = index < opt.reset_samples;
            step(sample, reset);
            ++index;
        }
    } else {
        std::string line;
        while (std::getline(in, line)) {
            if (line.empty()) continue;
            if (line[0] == '#') continue;
            std::istringstream iss(line);
            int64_t v = 0;
            if (!(iss >> v)) continue;

            int sample = opt.unsigned14 ? ClampUnsigned14(v) : ClampSigned14(v);
            if (opt.unsigned14) sample -= 8192;

            bool reset = index < opt.reset_samples;
            step(sample, reset);
            ++index;
        }
    }

    return 0;
}

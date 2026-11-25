/*
 * carlife-capture — capture SailfishOS screen (lipstick-recorder), encode
 * H.264 with x264 and write Annex-B elementary stream to stdout/FIFO.
 */
#include "recorder.h"
#include "convert.h"
#include "shmsource.h"
#include "x264_encoder.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <string>
#include <thread>
#include <chrono>
#include <queue>
#include <vector>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <sched.h>
#include <algorithm>

using namespace imira;

static volatile sig_atomic_t g_running = 1;
static void onSig(int) { g_running = 0; }
static_assert(ATOMIC_BOOL_LOCK_FREE == 2, "signal flag must be lock-free");
static std::atomic<bool> g_forceIdr{false};
static void onKeyframe(int) { g_forceIdr.store(true, std::memory_order_relaxed); }

static std::queue<std::vector<uint8_t>> g_frames;
static std::mutex g_mtx;
static std::condition_variable g_cv;
static std::atomic<bool> g_quit{false};

static void preferFastCores()
{
    cpu_set_t available, selected;
    if (sched_getaffinity(0, sizeof(available), &available)) return;
    unsigned long frequencies[CPU_SETSIZE] = {}, maximum = 0;
    for (int cpu=0;cpu<CPU_SETSIZE;++cpu) {
        if (!CPU_ISSET(cpu,&available)) continue;
        char path[128];
        snprintf(path,sizeof(path),"/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq",cpu);
        FILE *file=fopen(path,"r");
        if (file) { if (fscanf(file,"%lu",&frequencies[cpu])!=1) frequencies[cpu]=0; fclose(file); }
        maximum=std::max(maximum,frequencies[cpu]);
    }
    if (!maximum) return;
    CPU_ZERO(&selected);
    for (int cpu=0;cpu<CPU_SETSIZE;++cpu)
        if (CPU_ISSET(cpu,&available) && frequencies[cpu]*10>=maximum*9) CPU_SET(cpu,&selected);
    if (CPU_COUNT(&selected)>=2 && CPU_COUNT(&selected)<CPU_COUNT(&available) &&
            !sched_setaffinity(0,sizeof(selected),&selected))
        fprintf(stderr,"capture high-FPS affinity: %d fast cores (process only)\n",CPU_COUNT(&selected));
}

int main(int argc, char **argv)
{
    int width = 1920, height = 720, fps = 30, bitrate = 4000000;
    int rotation = 0;
    int nativeWidth = 0, nativeHeight = 0;
    const char *outPath = nullptr;
    const char *inputMode = "screen";
    for (int i = 1; i < argc - 1; i++) {
        std::string a = argv[i];
        if (a == "--native-width") nativeWidth = atoi(argv[++i]);
        else if (a == "--native-height") nativeHeight = atoi(argv[++i]);
        else if (a == "--width") width = atoi(argv[++i]);
        else if (a == "--height") height = atoi(argv[++i]);
        else if (a == "--fps") fps = atoi(argv[++i]);
        else if (a == "--bitrate") bitrate = atoi(argv[++i]);
        else if (a == "--rotation") rotation = atoi(argv[++i]);
        else if (a == "--out") outPath = argv[++i];
        else if (a == "--input") inputMode = argv[++i];
    }

    if (width < 2 || height < 2 || width > 7680 || height > 7680 ||
        width % 2 || height % 2 || fps < 1 || fps > 60 || bitrate < 500000 ||
        (rotation != 0 && rotation != 90 && rotation != 180 && rotation != 270)) {
        fprintf(stderr, "Invalid capture parameters\n"); return 2;
    }
    signal(SIGINT, onSig);
    signal(SIGTERM, onSig);
    signal(SIGUSR1, onKeyframe);
    // Writing to the video FIFO when no reader is attached (e.g. the car
    // disconnected between reconnects) must not kill us with SIGPIPE.
    signal(SIGPIPE, SIG_IGN);
    // Keep slice workers off slower cores in the explicit high-FPS mode.
    // This changes only our own affinity; every child thread inherits it.
    if (fps > 30) preferFastCores();

    FILE *out = stdout;
    if (outPath && strcmp(outPath, "-") != 0) {
        out = fopen(outPath, "wb");
        if (!out) {
            fprintf(stderr, "carlife-capture: cannot open %s\n", outPath);
            return 1;
        }
    }

    X264Encoder enc;
    if (!enc.init(width, height, fps, bitrate,
                  [&](const uint8_t *data, size_t size, bool idr) {
                      fwrite(data, 1, size, out);
                      fflush(out);
                  })) {
        fprintf(stderr, "carlife-capture: x264 init failed: %s\n",
                enc.lastError().c_str());
        if (out != stdout) fclose(out);
        return 1;
    }

    FrameConverter conv;
    conv.configure(width, height, false /* I420 */);

    std::thread encThread([&]() {
        auto report = std::chrono::steady_clock::now();
        double encodeMs = 0;
        unsigned count = 0;
        while (!g_quit) {
            std::vector<uint8_t> f;
            {
                std::unique_lock<std::mutex> lk(g_mtx);
                g_cv.wait(lk, [] { return !g_frames.empty() || g_quit; });
                if (g_quit && g_frames.empty()) break;
                f = std::move(g_frames.back());
                while (g_frames.size() > 1) g_frames.pop();
                g_frames.pop();
            }
            const auto before = std::chrono::steady_clock::now();
            if (!enc.encode(f.data(), f.size(), g_forceIdr.exchange(false)))
                fprintf(stderr, "carlife-capture: encode failed: %s\n",
                        enc.lastError().c_str());
            const auto now = std::chrono::steady_clock::now();
            encodeMs += std::chrono::duration<double, std::milli>(now - before).count();
            ++count;
            const double elapsed = std::chrono::duration<double>(now - report).count();
            if (elapsed >= 5) {
                fprintf(stderr, "capture stats: fps=%.1f encode_ms=%.1f\n", count / elapsed, encodeMs / count);
                report = now; count = 0; encodeMs = 0;
            }
        }
    });

    auto nextFrame = std::chrono::steady_clock::time_point();
    auto captureReport = std::chrono::steady_clock::now();
    double convertMs = 0;
    unsigned converted = 0, offered = 0;
    bool geometryReported = false;
    auto onFrame = [&](const uint8_t *pixels, int w, int h, int stride,
                       uint32_t drmFormat, int transform) {
        ++offered;
        if (!nativeWidth && !nativeHeight) {
            nativeWidth = w;
            nativeHeight = h;
        }
        if ((nativeWidth && nativeWidth != w) || (nativeHeight && nativeHeight != h)) {
            fprintf(stderr, "Native geometry mismatch: expected %dx%d, got %dx%d\n", nativeWidth, nativeHeight, w, h);
            g_running = 0; return;
        }
        if (!geometryReported) {
            fprintf(stderr, "capture native geometry: width=%d height=%d\n", w, h);
            geometryReported = true;
        }
        const auto now = std::chrono::steady_clock::now();
        const auto period = std::chrono::microseconds(1000000 / fps);
        if (nextFrame == std::chrono::steady_clock::time_point()) nextFrame = now;
        if (now < nextFrame) return;
        // Advance a clock: restarting it on each accepted frame collapses
        // a 43 FPS source to ~21 FPS when the requested output is 30 FPS.
        nextFrame += period;
        if (nextFrame < now) nextFrame = now + period;
        size_t sz = 0;
        uint8_t *frame = conv.convert(pixels, w, h, stride,
                                      transform == 2, rotation, &sz);
        const auto convertedAt = std::chrono::steady_clock::now();
        convertMs += std::chrono::duration<double, std::milli>(convertedAt - now).count();
        ++converted;
        const double elapsed = std::chrono::duration<double>(convertedAt - captureReport).count();
        if (elapsed >= 5) {
            fprintf(stderr, "capture source: offered_fps=%.1f converted_fps=%.1f convert_ms=%.1f native=%dx%d\n",
                    offered / elapsed, converted / elapsed, convertMs / converted, w, h);
            offered = converted = 0; convertMs = 0; captureReport = convertedAt;
        }
        if (frame) {
            {
                std::lock_guard<std::mutex> lk(g_mtx);
                while (!g_frames.empty()) g_frames.pop();
                g_frames.emplace(frame, frame + sz);
            }
            free(frame);
            g_cv.notify_one();
        }
    };

    bool sourceOk = false;
    if (strcmp(inputMode, "shm") == 0) {
        ShmFrameSource shmSrc;
        sourceOk = shmSrc.start(fps, onFrame);
        if (!sourceOk) {
            fprintf(stderr, "carlife-capture: shm source start failed\n");
        } else {
            fprintf(stderr, "carlife-capture: shm input mode\n");
            while (g_running)
                std::this_thread::sleep_for(std::chrono::milliseconds(400));
        }
        shmSrc.stop();
    } else {
        ScreenRecorder rec;
        sourceOk = rec.start(onFrame, fps > 30);
        if (!sourceOk) {
            fprintf(stderr, "carlife-capture: recorder start failed\n");
        } else {
            fprintf(stderr, "carlife-capture: streaming %dx%d@%d rot=%d -> %s\n",
                    width, height, fps, rotation, outPath ? outPath : "stdout");
            while (g_running) {
                if (fps <= 30) rec.requestRepaint();
                // A static lipstick screen otherwise only repaints every 400ms.
                // Request at the negotiated cadence; the callback also caps FPS.
                std::this_thread::sleep_for(std::chrono::microseconds(1000000 / fps));
            }
        }
        rec.stop();
    }

    if (!sourceOk) {
        g_quit = true;
        g_cv.notify_all();
        encThread.join();
        enc.stop();
        if (out != stdout) fclose(out);
        return 1;
    }

    g_quit = true;
    g_cv.notify_all();
    encThread.join();
    enc.stop();
    if (out != stdout) fclose(out);
    return 0;
}

#include "TransferFeedback.h"
#include "Translation.h"
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <thread>

namespace TransferFeedback {
    void End();
    namespace {
        using Clock = std::chrono::steady_clock;
        struct Request {
            std::function<void(Complete)> start;
            Clock::time_point began{Clock::now()}, phaseStart{began};
            Stage phase{Stage::Overlay};
            Report report;
            std::atomic<bool> cancelled{};
        };
        std::shared_ptr<Request> pending;
        std::atomic<bool> busy{};
        std::atomic<unsigned> renderedFrames{};
        std::mutex reportMutex;
        Report lastReport;
        bool registered{};
        std::string label;
        std::unique_ptr<SKSEMenuFramework::Model::HudElement> overlay;
        std::unique_ptr<SKSEMenuFramework::Model::InputEvent> input;

        void __stdcall Render() {
            if (!busy.load()) return;
            using namespace ImGuiMCP;
            const auto size = GetIO()->DisplaySize;
            if (size.x <= 0 || size.y <= 0) return;
            auto* canvas = GetForegroundDrawList();
            ImDrawListManager::AddRectFilled(canvas, {0, 0}, size, 0xE8000000, 0, 0);
            const auto text = CalcTextSize(label.c_str());
            const ImVec2 position{(size.x - text.x) * 0.5f, (size.y - text.y) * 0.5f};
            ImDrawListManager::AddText(canvas, position, 0xFFE0D4B5, label.c_str());
            ++renderedFrames;
        }

        bool __stdcall BlockInput(RE::InputEvent* event) {
            const auto* button = event ? event->AsButtonEvent() : nullptr;
            return busy.load() && button && !button->IsUp();
        }

        void Poll(const std::shared_ptr<Request>& request) {
            if (request->cancelled || pending != request) return;
            // Two render callbacks allow the first overlay frame to reach the screen.
            if (registered && renderedFrames.load() < 2 && Clock::now() - request->began < std::chrono::milliseconds(250)) {
                std::thread([request] {
                    std::this_thread::sleep_for(std::chrono::milliseconds(16));
                    if (!request->cancelled)
                        SKSE::GetTaskInterface()->AddTask([request] { Poll(request); });
                }).detach();
                return;
            }
            Mark(Stage::Inspection);
            auto start = std::move(request->start);
            try {
                if (start) start([request] {
                    if (request->cancelled || pending != request) return false;
                    End();
                    return true;
                });
                else End();
            } catch (...) { if (pending == request) Reset(); throw; }
        }
    }

    void Register() {
        if (registered || !SKSEMenuFramework::IsInstalled()) return;
        label = AVTranslation::Translate("Vault.Sorting");
        overlay.reset(SKSEMenuFramework::AddHudElement(Render));
        input.reset(SKSEMenuFramework::AddInputEvent(BlockInput));
        registered = overlay && input;
    }

    void Begin(std::function<void(Complete)> start) {
        if (busy.load()) return;
        auto request = std::make_shared<Request>();
        request->start = std::move(start);
        if (busy.exchange(true)) return;
        renderedFrames = 0;
        pending = request;
        Poll(request);
    }

    void Mark(Stage stage) {
        if (!pending) return;
        const auto now = Clock::now();
        pending->report.milliseconds[static_cast<unsigned>(pending->phase)] +=
            std::chrono::duration<double, std::milli>(now - pending->phaseStart).count();
        pending->phaseStart = now;
        pending->phase = stage;
    }

    void End() {
        if (!pending) return;
        Mark(pending->phase);
        pending->report.total = std::chrono::duration<double, std::milli>(Clock::now() - pending->began).count();
        pending->report.complete = true;
        {
            const std::lock_guard lock{reportMutex};
            lastReport = pending->report;
        }
        pending->cancelled = true;
        pending.reset();
        busy = false;
    }

    void Reset() {
        if (pending) pending->cancelled = true;
        pending.reset();
        busy = false;
        const std::lock_guard lock{reportMutex};
        lastReport = {};
    }

    Report LastReport() {
        const std::lock_guard lock{reportMutex};
        return lastReport;
    }
}

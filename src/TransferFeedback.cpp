#include "TransferFeedback.h"
#include "Translation.h"
#include <atomic>
#include <chrono>
#include <memory>
#include <algorithm>
#include <array>
#include <cmath>
#include <thread>

namespace TransferFeedback {
    void End();
    namespace {
        using Clock = std::chrono::steady_clock;
        struct Request {
            std::function<void(Complete)> start;
            Clock::time_point began{Clock::now()};
            unsigned frameTarget{2};
            std::function<bool(const std::function<bool()>&)> step;
            std::function<void()> complete;
            std::atomic<bool> cancelled{};
        };
        std::shared_ptr<Request> pending;
        std::atomic<bool> busy{};
        std::atomic<unsigned> renderedFrames{};
        bool registered{};
        std::string label;
        std::unique_ptr<SKSEMenuFramework::Model::HudElement> overlay;
        std::unique_ptr<SKSEMenuFramework::Model::InputEvent> input;
        struct FrameWait {
            std::shared_ptr<Request> owner;
            unsigned target;
            Clock::time_point began{Clock::now()};
            std::function<void()> work;
            std::function<void()> cancelled;
        };

        void Resume(const std::shared_ptr<FrameWait>& wait) {
            if (wait->owner && (wait->owner->cancelled || pending != wait->owner)) {
                auto cancelled = std::move(wait->cancelled);
                wait->work = {};
                if (cancelled) cancelled();
                return;
            }
            if (!wait->owner || !registered || renderedFrames.load() >= wait->target || Clock::now() - wait->began >= std::chrono::milliseconds(250)) {
                auto work = std::move(wait->work);
                if (work) work();
                return;
            }
            std::thread([wait] {
                std::this_thread::sleep_for(std::chrono::milliseconds(16));
                SKSE::GetTaskInterface()->AddTask([wait] { Resume(wait); });
            }).detach();
        }

        void __stdcall Render() {
            if (!busy.load()) return;
            using namespace ImGuiMCP;
            const auto size = GetIO()->DisplaySize;
            if (size.x <= 0 || size.y <= 0) return;
            auto* canvas = GetForegroundDrawList();
            const float scale = std::min({size.x / 480.0f, size.y / 720.0f, 2.0f});
            const auto text = CalcTextSize(label.c_str());
            const float width = std::max(340.0f * scale, text.x + 48.0f * scale);
            const float height = 140.0f * scale + text.y;
            const ImVec2 origin{(size.x - width) * 0.5f, (size.y - height) * 0.5f};
            const auto point = [origin, scale](float x, float y) {
                return ImVec2{origin.x + x * scale, origin.y + y * scale};
            };
            const float w = width / scale, h = height / scale;
            const std::array<ImVec2, 8> panel{point(9, 0), point(w - 9, 0), point(w, 9), point(w, h - 9),
                point(w - 9, h), point(9, h), point(0, h - 9), point(0, 9)};
            ImDrawListManager::AddRectFilled(canvas, {0, 0}, size, 0x42000000, 0, 0);
            ImDrawListManager::AddConvexPolyFilled(canvas, panel.data(), 8, 0xF30D0B08);
            ImDrawListManager::AddPolyline(canvas, panel.data(), 8, 0x8AA3B7B9, ImDrawFlags_Closed, scale);
            const float cx = w * 0.5f;
            ImDrawListManager::AddLine(canvas, point(cx - 102, 20), point(cx - 12, 20), 0x667F918F, scale);
            ImDrawListManager::AddLine(canvas, point(cx + 12, 20), point(cx + 102, 20), 0x667F918F, scale);
            const std::array<ImVec2, 4> ornament{point(cx, 17), point(cx + 3, 20), point(cx, 23), point(cx - 3, 20)};
            ImDrawListManager::AddPolyline(canvas, ornament.data(), 4, 0xAA8FBCCF, ImDrawFlags_Closed, scale);
            const auto sigil = [point, cx](float x, float y) { return point(cx + (x - 60) * 0.6f, 38 + y * 0.6f); };
            const float pulse = 0.5f - 0.5f * static_cast<float>(std::cos(GetTime() * 6.283185307179586 / 2.6));
            const auto gold = (static_cast<unsigned>(90 + 165 * pulse) << 24) | 0x008FBCCF;
            ImDrawListManager::AddCircle(canvas, sigil(60, 60), 29.4f * scale, 0x708FBCCF, 48, scale);
            const std::array<ImVec2, 3> upper{sigil(60, 23), sigil(92, 78), sigil(28, 78)};
            const std::array<ImVec2, 3> lower{sigil(60, 97), sigil(28, 42), sigil(92, 42)};
            ImDrawListManager::AddPolyline(canvas, upper.data(), 3, gold, ImDrawFlags_Closed, scale);
            ImDrawListManager::AddPolyline(canvas, lower.data(), 3, gold, ImDrawFlags_Closed, scale);
            const std::array<ImVec2, 4> diamond{sigil(60, 34), sigil(75, 60), sigil(60, 86), sigil(45, 60)};
            ImDrawListManager::AddPolyline(canvas, diamond.data(), 4, gold, ImDrawFlags_Closed, scale);
            const std::array<ImVec2, 4> core{sigil(60, 49), sigil(67, 60), sigil(60, 71), sigil(53, 60)};
            ImDrawListManager::AddConvexPolyFilled(canvas, core.data(), 4, gold);
            constexpr std::array<std::array<float, 4>, 14> strokes{{
                {60, 5, 60, 18}, {60, 102, 60, 115}, {5, 60, 18, 60}, {102, 60, 115, 60},
                {21, 21, 30, 30}, {90, 90, 99, 99}, {21, 99, 30, 90}, {90, 30, 99, 21},
                {38, 24, 38, 34}, {38, 34, 31, 34}, {82, 24, 82, 34}, {82, 34, 89, 34},
                {51, 103, 55, 94}, {65, 94, 69, 103}}};
            for (const auto& line : strokes)
                ImDrawListManager::AddLine(canvas, sigil(line[0], line[1]), sigil(line[2], line[3]), gold, scale);
            ImDrawListManager::AddText(canvas, {(size.x - text.x) * 0.5f, origin.y + 119.0f * scale}, 0xFFD9E2E5, label.c_str());
            ++renderedFrames;
        }

        bool __stdcall BlockInput(RE::InputEvent* event) {
            const auto* button = event ? event->AsButtonEvent() : nullptr;
            return busy.load() && button && !button->IsUp();
        }

        void Poll(const std::shared_ptr<Request>& request) {
            if (request->cancelled || pending != request) return;
            // Two render callbacks allow the first overlay frame to reach the screen.
            if (registered && renderedFrames.load() < request->frameTarget && Clock::now() - request->began < std::chrono::milliseconds(250)) {
                std::thread([request] {
                    std::this_thread::sleep_for(std::chrono::milliseconds(16));
                    if (!request->cancelled)
                        SKSE::GetTaskInterface()->AddTask([request] { Poll(request); });
                }).detach();
                return;
            }
            if (request->step) {
                try {
                    const std::function<bool()> active = [request] { return !request->cancelled && pending == request; };
                    auto step = request->step;
                    if (step(active)) {
                        if (!active()) return;
                        auto complete = std::move(request->complete);
                        request->step = {};
                        if (complete) complete(); else End();
                    } else if (active()) {
                        request->frameTarget = renderedFrames.load() + 1;
                        request->began = Clock::now();
                        std::thread([request] {
                            std::this_thread::sleep_for(std::chrono::milliseconds(16));
                            if (!request->cancelled) SKSE::GetTaskInterface()->AddTask([request] { Poll(request); });
                        }).detach();
                    }
                } catch (...) { if (pending == request) Reset(); throw; }
                return;
            }
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

    void Run(std::function<bool(const std::function<bool()>&)> step, std::function<void()> complete) {
        if (!pending || pending->cancelled) return;
        pending->step = std::move(step);
        pending->complete = std::move(complete);
        pending->frameTarget = renderedFrames.load() + 1;
        pending->began = Clock::now();
        auto request = pending;
        std::thread([request] {
            std::this_thread::sleep_for(std::chrono::milliseconds(16));
            if (!request->cancelled) SKSE::GetTaskInterface()->AddTask([request] { Poll(request); });
        }).detach();
    }

    void WaitForFrame(std::function<void()> work, std::function<void()> cancelled) {
        auto wait = std::make_shared<FrameWait>(FrameWait{pending, renderedFrames.load() + 1, Clock::now(), std::move(work), std::move(cancelled)});
        std::thread([wait] {
            std::this_thread::sleep_for(std::chrono::milliseconds(16));
            SKSE::GetTaskInterface()->AddTask([wait] { Resume(wait); });
        }).detach();
    }

    void End() {
        if (!pending) return;
        pending->cancelled = true;
        pending->step = {};
        pending->complete = {};
        pending.reset();
        busy = false;
    }

    void Reset() {
        if (pending) pending->cancelled = true;
        if (pending) { pending->step = {}; pending->complete = {}; pending->start = {}; }
        pending.reset();
        busy = false;
    }

}

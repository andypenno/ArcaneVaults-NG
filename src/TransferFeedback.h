#pragma once
#include <array>
#include <functional>

namespace TransferFeedback {
    enum class Stage { Overlay, Inspection, Recovery, Soulgems, Transfer, Count };
    struct Report {
        std::array<double, static_cast<unsigned>(Stage::Count)> milliseconds{};
        double total{};
        bool complete{};
    };
    void Register();
    using Complete = std::function<bool()>;
    void Begin(std::function<void(Complete)> start);
    void Mark(Stage stage);
    void Reset();
    Report LastReport();
}

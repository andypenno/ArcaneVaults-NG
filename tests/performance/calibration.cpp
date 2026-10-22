#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <vector>

int main() {
    using Clock = std::chrono::steady_clock;
    for (int sample = -2; sample < 4; ++sample) {
        const auto begin = Clock::now();
        std::uint64_t checksum{};
        for (int repeat = 0; repeat < 16; ++repeat) {
            std::vector<std::uint32_t> values(32768);
            std::uint32_t state = 42;
            for (auto& value : values) value = state = state * 1664525u + 1013904223u;
            std::sort(values.begin(), values.end());
            assert(std::is_sorted(values.begin(), values.end()));
            checksum += values.front() + static_cast<std::uint64_t>(values.back());
        }
        assert(checksum > 0);
        if (sample >= 0)
            std::cout << std::chrono::duration<double, std::milli>(Clock::now() - begin).count() << '\n';
    }
}

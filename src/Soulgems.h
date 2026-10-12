#pragma once
#include <optional>

namespace Soulgems {
    void Consolidate();
    void Recover();
    void Split();
    void Deposit(int a_keepEmpty, bool a_respectIgnores = false);
    void TakeEmpty(std::optional<int> a_target = std::nullopt);
    void BeginLoan(bool a_smithing);
    void EndLoan();
    void ResetLoan();
}

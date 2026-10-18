#pragma once
#include <optional>
#include <unordered_set>

namespace Soulgems {
    void Consolidate();
    void Recover(const std::unordered_set<RE::FormID>& a_sortExcluded = {});
    void Split();
    void Deposit(int a_keepEmpty, bool a_respectIgnores = false);
    void TakeEmpty(std::optional<int> a_target = std::nullopt);
    void BeginLoan(bool a_smithing, bool a_allMaterials = false);
    void EndLoan();
    void ResetLoan();
}

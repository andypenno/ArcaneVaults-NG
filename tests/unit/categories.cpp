#include <array>
#include <cassert>
#include <cstdint>
#include <set>
#include <string>
#include <string_view>
#include <utility>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"

int main() {
    std::set<std::string_view> names;
    std::set<ItemCategory> categories;
    for (const auto& [name, category] : categoryNames) {
        assert(!name.empty() && names.insert(name).second);
        assert(categories.insert(category).second);
        assert(category != ItemCategory::None && static_cast<unsigned>(category) < 64);
    }
    assert(ContainerTranslationKey(Container::None).empty());
    for (unsigned id = 1; id <= static_cast<unsigned>(Container::QuickTransfer); ++id) {
        const auto key = ContainerTranslationKey(static_cast<Container>(id));
        assert(!key.empty());
        assert(id == static_cast<unsigned>(Container::Ignore) ? key == "Ignore" : key.starts_with("Vault."));
    }
    assert(ContainerTranslationKey(static_cast<Container>(255)).empty());
}

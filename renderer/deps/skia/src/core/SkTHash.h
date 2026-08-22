/*
 * SkTHash.h — minimal stub for Fade's build.
 *
 * The real SkTHash.h is a private Skia source file that ships with Skia's
 * full source tree but not with our pre-built binary distribution.
 * SkResources.h pulls it in for skia_private::THashMap which is used by
 * the FileURIResourceProvider implementation — a feature we don't use.
 *
 * We only need the declaration to compile SkResources.h cleanly.
 * The actual THashMap implementation is compiled into skia.lib already.
 */
#pragma once
#ifndef SkTHash_DEFINED
#define SkTHash_DEFINED

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <utility>

namespace skia_private {

// Minimal forward declarations / stub implementations so SkResources.h
// can declare `mutable THashMap<SkString, sk_sp<ImageAsset>> fImageCache;`
// without the compiler needing the full definition.

template <typename K, typename V, typename HashT = std::hash<K>>
class THashMap {
public:
    THashMap()  = default;
    ~THashMap() = default;

    void set(const K&, V) {}
    V*   find(const K&) const { return nullptr; }
    void remove(const K&) {}
    void foreach(std::function<void(const K&, V*)>) const {}
    int  count() const { return 0; }
    void reset() {}
};

template <typename T, typename HashT = std::hash<T>>
class THashSet {
public:
    THashSet()  = default;
    ~THashSet() = default;
    void add(T) {}
    bool contains(const T&) const { return false; }
    void remove(const T&) {}
    int  count() const { return 0; }
    void reset() {}
};

} // namespace skia_private

#endif // SkTHash_DEFINED

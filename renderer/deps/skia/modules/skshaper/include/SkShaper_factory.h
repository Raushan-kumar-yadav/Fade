/*
 * SkShaper_factory.h — minimal stub for Fade's build.
 *
 * skia.lib is built with SVG support, so SkShapers::Factory symbols exist
 * in the binary. We only need the forward declaration to satisfy SkSVGDOM.h.
 * We never actually construct a Factory (SVGs with <text> fall back to
 * Skia's default rendering without shaping, which is fine for most assets).
 */
#ifndef SkShaper_factory_DEFINED
#define SkShaper_factory_DEFINED

#include "include/core/SkRefCnt.h"

// Forward-declare the Factory class that SkSVGDOM.h references.
namespace SkShapers {
class Factory : public SkRefCnt {};
} // namespace SkShapers

#endif // SkShaper_factory_DEFINED

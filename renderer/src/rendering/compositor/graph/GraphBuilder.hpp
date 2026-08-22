#pragma once

#include "RenderGraph.hpp"
#include "core/rendering/compositor/CacheEntry.hpp"
#include "core/rendering/timeline/Timeline.hpp"
#include <cstdint>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class Project;

class GraphBuilder {
public:
  static RenderGraph
  build(const std::vector<Timeline::ActiveClip> &activeClips,
        int64_t currentFrame,
        std::unordered_map<std::string, CacheEntry> *gpuTextureCache,
        Project *project = nullptr,
        std::unordered_set<std::string> parentVisited = {},
        const std::string &parentNestedId = "");

  GraphBuilder() = delete;
};

#include "GraphBuilder.hpp"
#include "RenderGraph.hpp"
#include "core/project/Project.hpp"
#include "core/rendering/clips/ShapeClip.hpp"
#include "core/rendering/clips/TextClip.hpp"
#include "core/rendering/clips/VideoClip.hpp"
#include "core/rendering/clips/adjustmentClip.hpp"
#include "core/rendering/clips/compClip.hpp"
#include "core/rendering/clips/imageClip.hpp"
#include "core/rendering/clips/lottieClip.hpp"
#include "core/rendering/clips/solidClip.hpp"
#include "core/rendering/clips/svgClip.hpp"
#include "core/rendering/compositor/passes/CameraEndNode.hpp"
#include "core/rendering/compositor/passes/CameraSetupNode.hpp"
#include "core/rendering/compositor/passes/ClipBeginNode.hpp"
#include "core/rendering/compositor/passes/ClipEndNode.hpp"
#include "core/rendering/compositor/passes/CompDrawNode.hpp"
#include "core/rendering/compositor/passes/DebugOverlayNode.hpp"
#include "core/rendering/compositor/passes/EffectNode.hpp"
#include "core/rendering/compositor/passes/ImageDrawNode.hpp"
#include "core/rendering/compositor/passes/LottieDrawNode.hpp"
#include "core/rendering/compositor/passes/MaskNode.hpp"
#include "core/rendering/compositor/passes/ShapeDrawNode.hpp"
#include "core/rendering/compositor/passes/SolidDrawNode.hpp"
#include "core/rendering/compositor/passes/SvgDrawNode.hpp"
#include "core/rendering/compositor/passes/TextDrawNode.hpp"
#include "core/rendering/compositor/passes/TrackMatteNode.hpp"
#include "core/rendering/compositor/passes/VideoDrawNode.hpp"
#include "core/rendering/compositor/passes/adjustmentNode.hpp"
#include "core/rendering/data/clipParam.hpp"
#include <memory>
#include <unordered_set>

static bool hasEffects(const std::shared_ptr<baseClip> &clip) {
  for (const auto &fx : clip->getEffects())
    if (fx->isEnabled())
      return true;
  return false;
}

static bool hasMasks(const std::shared_ptr<baseClip> &clip) {
  const auto *mg = clip->getMaskGroup();
  return mg && !mg->getMasks().empty();
}

static std::unique_ptr<RenderNode>
makeDrawNode(const std::shared_ptr<baseClip> &clip, int64_t currentFrame,
             Project *project, const std::unordered_set<std::string> &visited) {

  switch (clip->getType()) {

  case ClipType::solid: {
    auto n = std::make_unique<SolidDrawNode>();
    n->clip = static_cast<solidClip *>(clip.get());
    return n;
  }
  case ClipType::text: {
    auto n = std::make_unique<TextDrawNode>();
    n->clip = static_cast<TextClip *>(clip.get());
    return n;
  }
  case ClipType::video: {
    auto n = std::make_unique<VideoDrawNode>();
    n->clip = static_cast<VideoClip *>(clip.get());
    return n;
  }
  case ClipType::image: {
    auto n = std::make_unique<ImageDrawNode>();
    n->clip = static_cast<ImageClip *>(clip.get());
    return n;
  }
  case ClipType::shape: {
    auto n = std::make_unique<ShapeDrawNode>();
    n->clip = static_cast<ShapeClip *>(clip.get());
    return n;
  }
  case ClipType::SVG: {
    auto n = std::make_unique<SvgDrawNode>();
    n->clip = static_cast<svgClip *>(clip.get());
    return n;
  }
  case ClipType::Lottie: {
    auto n = std::make_unique<LottieDrawNode>();
    n->clip = static_cast<lottieClip *>(clip.get());
    return n;
  }
  case ClipType::comp: {
    auto n = std::make_unique<CompDrawNode>();
    n->clip = static_cast<compClip *>(clip.get());
    n->currentFrame = currentFrame;
    n->project = project;
    n->visited = visited; // thread cycle guard into sub-graph
    return n;
  }
  case ClipType::adjustment: {
    auto n = std::make_unique<adjustmentNode>();
    n->clip = static_cast<adjustmentClip *>(clip.get());
    n->currentFrame = currentFrame;
    return n;
  }
  default:
    return nullptr; // audio, subtitle
  }
}

RenderGraph GraphBuilder::build(
    const std::vector<Timeline::ActiveClip> &activeClips, int64_t currentFrame,
    std::unordered_map<std::string, CacheEntry> *gpuTextureCache,
    Project *project, std::unordered_set<std::string> parentVisited,
    const std::string &parentNestedId) {

  if (!parentNestedId.empty())
    parentVisited.insert(parentNestedId);

  RenderGraph graph;

  // Root — camera / viewport transform
  auto camNode = std::make_unique<CameraSetupNode>();
  camNode->nodeId = "camera_setup";
  camNode->priority = -1;
  graph.addNode(std::move(camNode));

  std::string prevId = "camera_setup";

  // Track-Matte pre-pass

  std::unordered_map<std::string, const Timeline::ActiveClip *> clipById;
  std::unordered_set<std::string> usedAsMatte;
  for (const auto &ac : activeClips) {
    clipById[ac.clip->getId()] = &ac;
    if (ac.clip->getTrackMatteType() != TrackMate::TrackMatteType::None) {
      const std::string &srcId = ac.clip->getTrackMatteClipId();
      if (!srcId.empty())
        usedAsMatte.insert(srcId);
    }
  }

  for (const auto &active : activeClips) {
    const std::string &clipId = active.clip->getId();
    const bool needsMask = hasMasks(active.clip);
    const bool needsEffect = hasEffects(active.clip);

    // kip here
    if (usedAsMatte.count(clipId))
      continue;

    const TrackMate::TrackMatteType tmType = active.clip->getTrackMatteType();
    bool handledByMatte = false;
    if (tmType != TrackMate::TrackMatteType::None) {
      const std::string &srcId = active.clip->getTrackMatteClipId();
      auto it = clipById.find(srcId);
      if (it != clipById.end()) {
        // Build TrackMatteNode
        auto contentDraw =
            makeDrawNode(active.clip, currentFrame, project, parentVisited);
        auto matteDraw = makeDrawNode(it->second->clip, currentFrame, project,
                                      parentVisited);

        if (contentDraw && matteDraw) {
          // ClipBeginNode for content
          auto begin = std::make_unique<ClipBeginNode>();
          begin->nodeId = "begin_" + clipId;
          begin->clip = active.clip;
          begin->hasMasks = needsMask;
          begin->priority = active.zOrder;
          begin->dependsOn = {prevId};
          graph.addNode(std::move(begin));
          prevId = "begin_" + clipId;

          // TrackMatteNode
          auto tmNode = std::make_unique<TrackMatteNode>();
          tmNode->nodeId = "trackmatte_" + clipId;
          tmNode->matteType = tmType;
          tmNode->priority = active.zOrder;
          tmNode->dependsOn = {prevId};
          tmNode->contentDrawNode = std::move(contentDraw);
          tmNode->matteDrawNode = std::move(matteDraw);
          graph.addNode(std::move(tmNode));
          prevId = "trackmatte_" + clipId;

          // MaskNode if needed
          if (needsMask) {
            auto mask = std::make_unique<MaskNode>();
            mask->nodeId = "mask_" + clipId;
            mask->clip = active.clip;
            mask->priority = active.zOrder;
            mask->dependsOn = {prevId};
            graph.addNode(std::move(mask));
            prevId = "mask_" + clipId;
          }

          // ClipEndNode
          auto end = std::make_unique<ClipEndNode>();
          end->nodeId = "end_" + clipId;
          end->needsRestore = needsMask;
          end->priority = active.zOrder;
          end->dependsOn = {prevId};
          graph.addNode(std::move(end));
          prevId = "end_" + clipId;

          handledByMatte = true;
        }
      }
    }
    if (handledByMatte)
      continue;

    {
      auto begin = std::make_unique<ClipBeginNode>();
      begin->nodeId = "begin_" + clipId;
      begin->clip = active.clip;
      begin->hasMasks = needsMask;
      begin->priority = active.zOrder;
      begin->dependsOn = {prevId};
      graph.addNode(std::move(begin));
      prevId = "begin_" + clipId;
    }

    // Draw or Effect node
    {
      auto drawNode =
          makeDrawNode(active.clip, currentFrame, project, parentVisited);
      if (!drawNode)
        continue; // non-visual

      const bool isAdjustment =
          (active.clip->getType() == ClipType::adjustment);

      if (needsEffect && !isAdjustment) {
        // EffectNode ownership
        auto fx = std::make_unique<EffectNode>();
        fx->nodeId = "fx_" + clipId;
        fx->clip = active.clip;
        fx->currentFrame = currentFrame;
        fx->drawNode = std::move(drawNode); // DrawNode
        fx->priority = active.zOrder;
        fx->dependsOn = {prevId};
        graph.addNode(std::move(fx));
        prevId = "fx_" + clipId;
      } else {

        drawNode->nodeId = "draw_" + clipId;
        drawNode->priority = active.zOrder;
        drawNode->dependsOn = {prevId};
        graph.addNode(std::move(drawNode));
        prevId = "draw_" + clipId;
      }
    }

    // MaskNode

    if (needsMask) {
      auto mask = std::make_unique<MaskNode>();
      mask->nodeId = "mask_" + clipId;
      mask->clip = active.clip;
      mask->priority = active.zOrder;
      mask->dependsOn = {prevId};
      graph.addNode(std::move(mask));
      prevId = "mask_" + clipId;
    }

    //   ClipEndNode

    {
      auto end = std::make_unique<ClipEndNode>();
      end->nodeId = "end_" + clipId;
      end->needsRestore = needsMask;
      end->priority = active.zOrder;
      end->dependsOn = {prevId};
      graph.addNode(std::move(end));
      prevId = "end_" + clipId;
    }
  }

  {
    auto cameraEnd = std::make_unique<CameraEndNode>();
    cameraEnd->nodeId = "camera_end";
    cameraEnd->dependsOn = {prevId};
    graph.addNode(std::move(cameraEnd));
  }

  //   DebugOverlayNode
  {
    auto dbg = std::make_unique<DebugOverlayNode>();
    dbg->nodeId = "debug_overlay";
    dbg->clipCount = static_cast<int>(activeClips.size());
    dbg->nodeCount = static_cast<int>(graph.nodeCount()) + 1;
    dbg->priority = 9999;
    dbg->dependsOn = {"camera_end"};
    graph.addNode(std::move(dbg));
  }

  return graph;
}
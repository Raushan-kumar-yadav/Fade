#include "CompDrawNode.hpp"
#include "core/SkCanvas.h"
#include "core/SkImageInfo.h"
#include "core/api/Logger.hpp"
#include "core/project/Project.hpp"
#include "core/rendering/clips/compClip.hpp"
#include "core/rendering/compositor/graph/GraphBuilder.hpp"
#include "core/rendering/compositor/graph/RenderGraph.hpp"
#include "core/rendering/timeline/Timeline.hpp"
#include "gpu/ganesh/GrDirectContext.h"
#include "gpu/ganesh/SkSurfaceGanesh.h"
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <shared_mutex>

void CompDrawNode::execute(RenderContext &ctx) {
  if (!ctx.canvas || !clip || !ctx.grCtx || !project)
    return;

  const std::string &nestedId = clip->getNestedTimelineId();
  if (nestedId.empty())
    return;

  // Cycle detection
  if (visited.count(nestedId)) {
    LOG_WARN("[CompDrawNode] Circular comp reference '" + nestedId +
             "' — skipping to prevent infinite recursion.");
    return;
  }

  Timeline *nested = project->getTimelineById(nestedId);
  if (!nested)
    return;

  const int w = clip->getWidth();
  const int h = clip->getHeight();
  if (w <= 0 || h <= 0)
    return;

  // Convert global frame to comp-local frame
  int64_t localFrame =
      std::max<int64_t>(0, currentFrame - clip->getStartFrame());

  std::vector<Timeline::ActiveClip> subClips;
  {
    std::shared_lock lk(nested->rwLock());
    subClips = nested->getActiveClipsAt(localFrame);
    for (auto &ac : subClips)
      if (ac.clip)
        ac.clip->evaluateAll(localFrame);
  }

  if (subClips.empty())
    return;

  //   offscreen GPU surface
  SkImageInfo ii = SkImageInfo::MakeN32Premul(w, h);
  auto offscreen =
      SkSurfaces::RenderTarget(ctx.grCtx, skgpu::Budgeted::kYes, ii);
  if (!offscreen)
    return;

  SkCanvas *offCvs = offscreen->getCanvas();
  offCvs->clear(SK_ColorTRANSPARENT);

  // Build and execute sub-graph
  RenderContext subCtx = ctx;
  subCtx.canvas = offCvs;
  subCtx.width = static_cast<float>(w);
  subCtx.height = static_cast<float>(h);
  subCtx.panX = subCtx.panY = 0.f;
  subCtx.zoom = 1.f;

  subCtx.currentFrame = localFrame;

  subCtx.clipIdPrefix = ctx.clipIdPrefix + clip->getId() + "_";

  RenderGraph subGraph = GraphBuilder::build(
      subClips, localFrame, ctx.gpuTextureCache, project, visited, nestedId);

  if (!subGraph.compile()) {
    LOG_WARN("[CompDrawNode] Sub-graph cycle detected for comp '" + nestedId +
             "'");
    return;
  }
  subGraph.execute(subCtx);

  sk_sp<SkImage> compImg = offscreen->makeImageSnapshot();
  if (!compImg)
    return;

  for (const auto &fx : clip->getEffects()) {
    if (!fx->isEnabled())
      continue;
    sk_sp<SkImage> processed = fx->apply(compImg, currentFrame, ctx.grCtx);
    if (processed)
      compImg = std::move(processed);
  }

  const glm::mat4 scaledM =
      glm::scale(clip->getWorldTransform(),
                 glm::vec3(static_cast<float>(w), static_cast<float>(h), 1.f));

  SkM44 skModel(scaledM[0][0], scaledM[1][0], scaledM[2][0], scaledM[3][0],
                scaledM[0][1], scaledM[1][1], scaledM[2][1], scaledM[3][1],
                scaledM[0][2], scaledM[1][2], scaledM[2][2], scaledM[3][2],
                scaledM[0][3], scaledM[1][3], scaledM[2][3], scaledM[3][3]);

  SkPaint paint;
  paint.setAlphaf(clip->getOpacity());
  paint.setAntiAlias(true);
  SkSamplingOptions sampling(SkFilterMode::kLinear, SkMipmapMode::kLinear);

  SkRect src = SkRect::MakeWH(static_cast<float>(w), static_cast<float>(h));
  SkRect dst = SkRect::MakeLTRB(-0.5f, -0.5f, 0.5f, 0.5f);

  ctx.canvas->save();
  ctx.canvas->concat(skModel);
  ctx.canvas->drawImageRect(compImg, src, dst, sampling, &paint,
                            SkCanvas::kStrict_SrcRectConstraint);
  ctx.canvas->restore();
}

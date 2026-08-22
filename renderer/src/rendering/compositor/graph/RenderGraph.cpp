#include "RenderGraph.hpp"
#include "core/api/Logger.hpp"
#include <algorithm>

void RenderGraph::addNode(std::unique_ptr<RenderNode> node) {
  if (!node)
    return;

  const std::string &id = node->nodeId;
  if (m_nodeMap.count(id)) {
    LOG_WARN("[RenderGraph] Duplicate node ID: " + id);
    return;
  }

  m_nodeMap[id] = node.get();
  m_nodes.push_back(std::move(node));
  m_compiled = false;
}

bool RenderGraph::compile() {
  m_waves.clear();
  m_hasCycle = false;
  m_compiled = true;

  const size_t n = m_nodes.size();
  if (n == 0)
    return true;

  std::unordered_map<std::string, std::vector<std::string>> adjacency;
  std::unordered_map<std::string, int> inDegree;

  for (const auto &node : m_nodes) {
    inDegree[node->nodeId] = 0;
    adjacency[node->nodeId] = {};
  }

  for (const auto &node : m_nodes) {
    for (const auto &depId : node->dependsOn) {
      if (!m_nodeMap.count(depId))
        continue;
      adjacency[depId].push_back(node->nodeId);
      inDegree[node->nodeId]++;
    }
  }

  std::vector<RenderNode *> currentWave;
  for (const auto &[id, deg] : inDegree) {
    if (deg == 0)
      currentWave.push_back(m_nodeMap[id]);
  }

  size_t processed = 0;

  while (!currentWave.empty()) {
    // Sort by priority within wave (z-order)
    std::sort(
        currentWave.begin(), currentWave.end(),
        [](RenderNode *a, RenderNode *b) { return a->priority < b->priority; });

    m_waves.push_back(currentWave);
    processed += currentWave.size();

    // Find next wave
    std::vector<RenderNode *> nextWave;
    for (RenderNode *node : currentWave) {
      for (const auto &neighborId : adjacency[node->nodeId]) {
        if (--inDegree[neighborId] == 0)
          nextWave.push_back(m_nodeMap[neighborId]);
      }
    }
    currentWave = std::move(nextWave);
  }

  if (processed != n) {
    m_hasCycle = true;
    m_waves.clear();
    return false;
  }

  return true;
}

void RenderGraph::execute(RenderContext &ctx) {
  if (!m_compiled || m_hasCycle)
    return;

  for (const auto &wave : m_waves) {
    // parallel prepare
    for (RenderNode *node : wave)
      node->prepare(ctx);

    // equential draw (render thread, z-ordered)
    for (RenderNode *node : wave)
      node->execute(ctx);
  }
}

void RenderGraph::clear() {
  m_waves.clear();
  m_nodeMap.clear();
  m_nodes.clear();
  m_compiled = false;
  m_hasCycle = false;
}

#pragma once

#include "RenderNode.hpp"
#include <cstddef>
#include <memory>
#include <vector>
class RenderGraph {
public:
  RenderGraph() = default;
  ~RenderGraph() = default;

  RenderGraph(RenderGraph &&) = default;
  RenderGraph &operator=(RenderGraph &&) = default;
  RenderGraph(const RenderGraph &) = delete;
  RenderGraph &operator=(const RenderGraph &) = delete;

  void addNode(std::unique_ptr<RenderNode> node);
  bool compile();
  void execute(RenderContext &ctx);

  bool hasCycle() const { return m_hasCycle; }
  size_t nodeCount() const { return m_nodes.size(); }

  const std::vector<RenderNode *> &getExecutionOrder() const {
    return m_executionOrder;
  }
  void clear();

private:
  std::vector<std::unique_ptr<RenderNode>> m_nodes;
  std::unordered_map<std::string, RenderNode *> m_nodeMap;
  std::vector<RenderNode *> m_executionOrder;
  std::vector<std::vector<RenderNode *>> m_waves;

  bool m_compiled = false;
  bool m_hasCycle = false;
};
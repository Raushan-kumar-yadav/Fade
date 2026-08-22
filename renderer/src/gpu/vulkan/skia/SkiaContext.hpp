#pragma once
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "gpu/ganesh/GrDirectContext.h"
#include <memory>

class SkiaContext {
public:
  SkiaContext(DeviceContext *deviceContext);
  ~SkiaContext();

  GrDirectContext *getDirectContext() const { return fDirectContext.get(); }

  void Init(DeviceContext *deviceContext);

private:
  sk_sp<GrDirectContext> fDirectContext;
  void *fVmaAllocator = nullptr;
};
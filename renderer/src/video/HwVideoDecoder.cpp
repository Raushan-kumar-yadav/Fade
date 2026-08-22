#include "video/HwVideoDecoder.hpp"

AVPixelFormat HWVideoDecoder::getHwFormat(AVCodecContext *ctx,
                                          const AVPixelFormat *pix_fmts) {
  for (const AVPixelFormat *p = pix_fmts; *p != -1; p++) {
    if (*p == AV_PIX_FMT_VULKAN) {
      return *p;
    }
  }
  LOG_WARN("HWVideoDecoder: Vulkan pixel format not found. Falling back to "
           "software.");
  return AV_PIX_FMT_NONE;
}

AVPixelFormat
HWVideoDecoder::get_format_callback(AVCodecContext *ctx,
                                    const AVPixelFormat *pix_fmts) {
  HWVideoDecoder *self = static_cast<HWVideoDecoder *>(ctx->opaque);

  if (self && self->m_hwaccelFailed) {
    LOG_WARN("HW accel previously failed. Rejecting HW format.");
    return AV_PIX_FMT_NONE;
  }

  for (const AVPixelFormat *p = pix_fmts; *p != -1; p++) {
    if (*p == AV_PIX_FMT_D3D11) {
      // Only log on first call — this fires on flush/reinit, not per frame
      static bool logged = false;
      if (!logged) { LOG_INFO("FFmpeg requested D3D11 format - Handshake SUCCESSFUL"); logged = true; }
      return *p;
    }
  }

  if (self) {
    self->m_hwaccelFailed = true;
  }
  LOG_WARN("FFmpeg did NOT offer D3D11 format. HW acceleration will fail.");
  return AV_PIX_FMT_NONE;
}

HWVideoDecoder::HWVideoDecoder(const std::string &filepath,
                               DeviceContext *context, float previewScale)
    : m_context(context), m_lastDecodedFrame(-1), m_previewScale(previewScale) {
  if (!m_context) {
    throw std::runtime_error(
        "CRITICAL: DeviceContext is NULL inside HWVideoDecoder!");
  }

  if (avformat_open_input(&m_formatCtx, filepath.c_str(), nullptr, nullptr) !=
      0) {
    throw std::runtime_error("failed to open video file");
  }

  avformat_find_stream_info(m_formatCtx, nullptr);

  const AVCodec *decoder = nullptr;
  m_videoStreamIndex =
      av_find_best_stream(m_formatCtx, AVMEDIA_TYPE_VIDEO, -1, -1, &decoder, 0);

  if (m_videoStreamIndex < 0) {
    throw std::runtime_error("No video stream found in file");
  }

  m_codecCtx = avcodec_alloc_context3(decoder);
  avcodec_parameters_to_context(
      m_codecCtx, m_formatCtx->streams[m_videoStreamIndex]->codecpar);

  initHardwareContext();

  m_codecCtx->hw_device_ctx = av_buffer_ref(m_hwDeviceCtx);
  m_codecCtx->get_format = get_format_callback;
  m_codecCtx->opaque = this;

  if (avcodec_open2(m_codecCtx, decoder, nullptr) < 0) {
    throw std::runtime_error("Failed to open HW codec");
  }

  {
    AVPacket *probePacket = av_packet_alloc();
    AVFrame *probeFrame = av_frame_alloc();
    bool formatNegotiated = false;
    int maxProbePackets = 30;

    for (int i = 0;
         i < maxProbePackets && !formatNegotiated && !m_hwaccelFailed; ++i) {
      if (av_read_frame(m_formatCtx, probePacket) < 0)
        break;

      if (probePacket->stream_index == m_videoStreamIndex) {
        avcodec_send_packet(m_codecCtx, probePacket);
        int ret = avcodec_receive_frame(m_codecCtx, probeFrame);
        if (ret == 0) {
          formatNegotiated = true;
          av_frame_unref(probeFrame);
        }
      }
      av_packet_unref(probePacket);
    }

    av_frame_free(&probeFrame);
    av_packet_free(&probePacket);

    av_seek_frame(m_formatCtx, m_videoStreamIndex, 0, AVSEEK_FLAG_BACKWARD);
    avcodec_flush_buffers(m_codecCtx);
  }

  if (m_hwaccelFailed || m_codecCtx->pix_fmt != AV_PIX_FMT_D3D11) {
    throw std::runtime_error("D3D11 hwaccel rejected by FFmpeg - GPU lacks "
                             "working video decode support");
  }
  LOG_INFO("D3D11 Hardware Pipeline ACTIVE for: " + filepath);

  m_timeBase = m_formatCtx->streams[m_videoStreamIndex]->time_base;
  m_fps = av_q2d(m_formatCtx->streams[m_videoStreamIndex]->avg_frame_rate);
  m_width = m_codecCtx->width;
  m_height = m_codecCtx->height;

  int64_t durationFrames = m_formatCtx->streams[m_videoStreamIndex]->duration;
  if (durationFrames != AV_NOPTS_VALUE) {
    m_duration = durationFrames * av_q2d(m_timeBase);
  } else {
    m_duration = m_formatCtx->duration / (double)AV_TIME_BASE;
  }
}

HWVideoDecoder::~HWVideoDecoder() {
  if (m_swsCtx)
    sws_freeContext(m_swsCtx);
  if (m_rgbBuffer)
    av_free(m_rgbBuffer);
  if (m_rgbFrame)
    av_frame_free(&m_rgbFrame);

  // free up context
  if (m_codecCtx)
    avcodec_free_context(&m_codecCtx);

  // free up buffer
  if (m_formatCtx)
    avformat_close_input(&m_formatCtx);
  if (m_hwDeviceCtx)
    av_buffer_unref(&m_hwDeviceCtx);
}

void HWVideoDecoder::initHardwareContext() {
  int ret = av_hwdevice_ctx_create(&m_hwDeviceCtx, AV_HWDEVICE_TYPE_D3D11VA,
                                   nullptr, nullptr, 0);
  if (ret < 0) {
    char errbuf[AV_ERROR_MAX_STRING_SIZE];
    av_strerror(ret, errbuf, sizeof(errbuf));
    throw std::runtime_error("Failed to initialize D3D11VA HW context: " +
                             std::string(errbuf));
  }

  LOG_INFO(
      "[HWVideoDecoder] D3D11VA HW device context initialized successfully!");
}

std::shared_ptr<DecodedFrame> HWVideoDecoder::decodeFrame(int64_t targetFrame) {

  auto decodeStart = std::chrono::steady_clock::now();

  //  THE SEEK BLOCK
  // Only seek+flush on:
  //   - backward seeks (targetFrame < m_lastDecodedFrame)
  //   - large forward jumps (> 60 frames ahead — past the drain window)
  //   - first call (m_lastDecodedFrame == -1)
  const int64_t gap = targetFrame - m_lastDecodedFrame;
  const bool needSeek = (m_lastDecodedFrame < 0) || (gap < 0) || (gap > 60);

  if (needSeek) {
    std::cout << "[DECODE] SEEK  target=" << targetFrame
              << " last=" << m_lastDecodedFrame
              << " gap=" << gap << "\n" << std::flush;
    double timeInSecond = static_cast<double>(targetFrame) / m_fps;
    int64_t target_pts = static_cast<int64_t>(std::round(timeInSecond / av_q2d(m_timeBase)));

    // Jump to the nearest keyframe before target
    av_seek_frame(m_formatCtx, m_videoStreamIndex, target_pts,
                  AVSEEK_FLAG_BACKWARD);
    // Flush codec buffers — triggers get_format_callback re-negotiation
    avcodec_flush_buffers(m_codecCtx);

    m_lastDecodedFrame = -1;
  }

  AVFrame *frame = av_frame_alloc();
  AVPacket *packet = av_packet_alloc();

  if (!frame || !packet)
    return nullptr;

  std::shared_ptr<DecodedFrame> decoded = nullptr;

  //  THE PUMP LOOP
  const int MAX_DECODE_RETRIES = 500;
  int retryCount = 0;

  while (true) {
    int response = avcodec_receive_frame(m_codecCtx, frame);

    if (response == 0) {

      //  THE TIME MATH
      double timestamp_sec = frame->pts * av_q2d(m_timeBase);
      int64_t current_frame_idx = std::round(timestamp_sec * m_fps);

      if (current_frame_idx < targetFrame) {
        av_frame_unref(frame);
        continue;
      }

      //  WE FOUND THE TARGET FRAME
      decoded = std::make_shared<DecodedFrame>();
      decoded->width = frame->width;
      decoded->height = frame->height;
      decoded->pts = frame->pts;
      decoded->frameNumber = current_frame_idx;

      if (frame->format == AV_PIX_FMT_D3D11) {

        AVFrame *cpuFrame = av_frame_alloc();
        if (!cpuFrame) {
          LOG_ERROR("HW decode: failed to alloc CPU frame for transfer");
          decoded = nullptr;
          break;
        }

        int transferRet = av_hwframe_transfer_data(cpuFrame, frame, 0);

        // Release the GPU AVFrame immediately
        av_frame_unref(frame);

        if (transferRet < 0) {
          char errbuf[AV_ERROR_MAX_STRING_SIZE];
          av_strerror(transferRet, errbuf, sizeof(errbuf));
          LOG_ERROR("HW decode: av_hwframe_transfer_data failed: " +
                    std::string(errbuf));
          av_frame_free(&cpuFrame);
          decoded = nullptr;
          break;
        }

        // Log actual transfer format (one-time)
        static bool formatLogged = false;
        if (!formatLogged) {
          LOG_INFO("[HWVideoDecoder] Transfer format: " +
                   std::to_string(cpuFrame->format) +
                   " (NV12=" + std::to_string(AV_PIX_FMT_NV12) +
                   ", YUV420P=" + std::to_string(AV_PIX_FMT_YUV420P) + ")");
          LOG_INFO("[HWVideoDecoder] Transfer dims: " +
                   std::to_string(cpuFrame->width) + "x" +
                   std::to_string(cpuFrame->height) +
                   " linesize[0]=" + std::to_string(cpuFrame->linesize[0]) +
                   " linesize[1]=" + std::to_string(cpuFrame->linesize[1]));
          formatLogged = true;
        }

        int srcW = cpuFrame->width;
        int srcH = cpuFrame->height;
        // Preview downscale: sws_scale does NV12→RGBA + resize in one SIMD pass
        int dstW = std::max(2, static_cast<int>(srcW * m_previewScale)) & ~1; // ensure even
        int dstH = std::max(2, static_cast<int>(srcH * m_previewScale)) & ~1;

        decoded->type = FrameType::SOFTWARE_RGBA;
        decoded->width = dstW;
        decoded->height = dstH;
        decoded->isStatic = false;

        // Re-enter allocation block if sws exists (from decodeFrameDirect) but
        // m_rgbFrame/m_rgbBuffer were never allocated (direct-decode skips them).
        if (!m_swsCtx || !m_rgbFrame || !m_rgbBuffer ||
            m_srcWidth != srcW || m_srcHeight != srcH ||
            m_width != dstW || m_height != dstH) {
          if (m_swsCtx)
            sws_freeContext(m_swsCtx);
          if (m_rgbBuffer)
            av_free(m_rgbBuffer);
          if (m_rgbFrame)
            av_frame_free(&m_rgbFrame);

          m_srcWidth = srcW;
          m_srcHeight = srcH;
          m_width = dstW;
          m_height = dstH;
          m_swsCtx = sws_getContext(
              srcW, srcH, (AVPixelFormat)cpuFrame->format, dstW, dstH,
              AV_PIX_FMT_RGBA, SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
          // Some NV12 variants fail with FAST_BILINEAR — try BILINEAR fallback
          if (!m_swsCtx)
              m_swsCtx = sws_getContext(
                  srcW, srcH, (AVPixelFormat)cpuFrame->format, dstW, dstH,
                  AV_PIX_FMT_RGBA, SWS_BILINEAR, nullptr, nullptr, nullptr);
          m_rgbFrame = av_frame_alloc();
          int numBytes =
              av_image_get_buffer_size(AV_PIX_FMT_RGBA, dstW, dstH, 1);
          m_rgbBuffer = (uint8_t *)av_malloc(numBytes * sizeof(uint8_t));
          av_image_fill_arrays(m_rgbFrame->data, m_rgbFrame->linesize,
                               m_rgbBuffer, AV_PIX_FMT_RGBA, dstW, dstH, 1);
          LOG_INFO("[HWVideoDecoder] Preview scale: " + std::to_string(srcW) + "x" +
                   std::to_string(srcH) + " -> " + std::to_string(dstW) + "x" + std::to_string(dstH));
        }

        if (m_swsCtx && m_rgbFrame && m_rgbBuffer) {
          sws_scale(m_swsCtx, (uint8_t const *const *)cpuFrame->data,
                    cpuFrame->linesize, 0, srcH, m_rgbFrame->data,
                    m_rgbFrame->linesize);
          size_t totalBytes = static_cast<size_t>(dstW) * dstH * 4;
          decoded->dataRGBA.resize(totalBytes);
          if (m_rgbFrame->linesize[0] == static_cast<int>(dstW * 4)) {
            memcpy(decoded->dataRGBA.data(), m_rgbFrame->data[0], totalBytes);
          } else {
            for (int y = 0; y < dstH; ++y) {
              memcpy(decoded->dataRGBA.data() + y * dstW * 4,
                     m_rgbFrame->data[0] + y * m_rgbFrame->linesize[0],
                     dstW * 4);
            }
          }
        } else {
          LOG_ERROR("HWVideoDecoder: sws_scale context setup failed");
          decoded->valid = false;
          decoded = nullptr;
        }

        av_frame_free(&cpuFrame);
        // NOTE: frame was already released via av_frame_unref() above — do NOT
        // call av_frame_free(&frame) here, only free the shell allocation.
        av_frame_free(&frame);
      } else {

        // SOFTWARE FALLBACK inside HWVideoDecoder
        int srcW = frame->width;
        int srcH = frame->height;
        int dstW = std::max(2, static_cast<int>(srcW * m_previewScale)) & ~1;
        int dstH = std::max(2, static_cast<int>(srcH * m_previewScale)) & ~1;
        decoded->type = FrameType::SOFTWARE_RGBA;
        decoded->width = dstW;
        decoded->height = dstH;
        decoded->isStatic = false;

        if (!m_swsCtx || !m_rgbFrame || !m_rgbBuffer || m_srcWidth != srcW || m_srcHeight != srcH || m_width != dstW || m_height != dstH) {
          if (m_swsCtx)
            sws_freeContext(m_swsCtx);
          if (m_rgbBuffer)
            av_free(m_rgbBuffer);
          if (m_rgbFrame)
            av_frame_free(&m_rgbFrame);

          m_srcWidth = srcW;
          m_srcHeight = srcH;
          m_width = dstW;
          m_height = dstH;
          m_swsCtx = sws_getContext(
              srcW, srcH, (AVPixelFormat)frame->format, dstW, dstH,
              AV_PIX_FMT_RGBA, SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
          if (!m_swsCtx)
              m_swsCtx = sws_getContext(
                  srcW, srcH, (AVPixelFormat)frame->format, dstW, dstH,
                  AV_PIX_FMT_RGBA, SWS_BILINEAR, nullptr, nullptr, nullptr);
          m_rgbFrame = av_frame_alloc();
          int numBytes =
              av_image_get_buffer_size(AV_PIX_FMT_RGBA, dstW, dstH, 1);
          m_rgbBuffer = (uint8_t *)av_malloc(numBytes * sizeof(uint8_t));
          av_image_fill_arrays(m_rgbFrame->data, m_rgbFrame->linesize,
                               m_rgbBuffer, AV_PIX_FMT_RGBA, dstW, dstH, 1);
        }

        if (m_swsCtx && m_rgbFrame && m_rgbBuffer) {
          sws_scale(m_swsCtx, (uint8_t const *const *)frame->data,
                    frame->linesize, 0, srcH, m_rgbFrame->data,
                    m_rgbFrame->linesize);
          size_t totalBytes = static_cast<size_t>(dstW) * dstH * 4;
          decoded->dataRGBA.resize(totalBytes);
          if (m_rgbFrame->linesize[0] == static_cast<int>(dstW * 4)) {
            memcpy(decoded->dataRGBA.data(), m_rgbFrame->data[0], totalBytes);
          } else {
            for (int y = 0; y < dstH; ++y) {
              memcpy(decoded->dataRGBA.data() + y * dstW * 4,
                     m_rgbFrame->data[0] + y * m_rgbFrame->linesize[0],
                     dstW * 4);
            }
          }
        } else {
          LOG_ERROR("HWVideoDecoder fallback: sws_scale context setup failed");
          decoded = nullptr;
        }

        av_frame_free(&frame); // cope to RAM
      }

      // Only mark valid if we successfully decoded pixels
      if (decoded)
        decoded->valid = true;
      m_lastDecodedFrame = current_frame_idx;

      // Log what was actually decoded vs what was requested
      auto decodeEnd = std::chrono::steady_clock::now();
      double decMs = std::chrono::duration_cast<std::chrono::microseconds>(decodeEnd - decodeStart).count() / 1000.0;
      if (current_frame_idx != targetFrame) {
        std::cout << "[DECODE] MISMATCH request=" << targetFrame
                  << " got=" << current_frame_idx
                  << " diff=" << (current_frame_idx - targetFrame)
                  << " dt=" << decMs << "ms\n" << std::flush;
      } else {
        std::cout << "[DECODE] OK frame=" << targetFrame << " dt=" << decMs << "ms\n" << std::flush;
      }
      break;

    }

    else if (response == AVERROR(EAGAIN)) {

      if (++retryCount > MAX_DECODE_RETRIES) {
        LOG_ERROR("HW decoder exceeded max retry limit (" +
                  std::to_string(MAX_DECODE_RETRIES) + ") for frame " +
                  std::to_string(targetFrame));
        break;
      }

      // need more packets from video file
      if (av_read_frame(m_formatCtx, packet) >= 0) {
        if (packet->stream_index == m_videoStreamIndex) {
          avcodec_send_packet(m_codecCtx, packet);
        }
        av_packet_unref(packet);
      } else {
        avcodec_send_packet(m_codecCtx, nullptr);
      }
    } else if (response == AVERROR_EOF) {
      break;
    } else {
      break;
    }
  }

  av_packet_free(&packet);
  if (!decoded) {
    av_frame_free(&frame);
  }

  return decoded;
}

// ── Zero-copy decode: sws_scale writes RGBA directly to dstBuffer ────────
bool HWVideoDecoder::decodeFrameDirect(int64_t targetFrame, uint8_t* dstBuffer,
                                       int dstW, int dstH) {
  if (!dstBuffer || dstW <= 0 || dstH <= 0) return false;

  auto decodeStart = std::chrono::steady_clock::now();

  // SEEK BLOCK (identical to decodeFrame)
  const int64_t gap = targetFrame - m_lastDecodedFrame;
  const bool needSeek = (m_lastDecodedFrame < 0) || (gap < 0) || (gap > 60);

  if (needSeek) {
    std::cout << "[DECODE-D] SEEK target=" << targetFrame
              << " last=" << m_lastDecodedFrame
              << " gap=" << gap << "\n" << std::flush;
    double timeInSecond = static_cast<double>(targetFrame) / m_fps;
    int64_t target_pts = static_cast<int64_t>(std::round(timeInSecond / av_q2d(m_timeBase)));
    av_seek_frame(m_formatCtx, m_videoStreamIndex, target_pts, AVSEEK_FLAG_BACKWARD);
    avcodec_flush_buffers(m_codecCtx);
    m_lastDecodedFrame = -1;
  }

  AVFrame *frame = av_frame_alloc();
  AVPacket *packet = av_packet_alloc();
  if (!frame || !packet) return false;

  bool success = false;
  const int MAX_DECODE_RETRIES = 500;
  int retryCount = 0;

  while (true) {
    int response = avcodec_receive_frame(m_codecCtx, frame);

    if (response == 0) {
      double timestamp_sec = frame->pts * av_q2d(m_timeBase);
      int64_t current_frame_idx = std::round(timestamp_sec * m_fps);

      if (current_frame_idx < targetFrame) {
        av_frame_unref(frame);
        continue;
      }

      // FOUND TARGET — D3D11 HW path
      if (frame->format == AV_PIX_FMT_D3D11) {
        AVFrame *cpuFrame = av_frame_alloc();
        if (!cpuFrame) { break; }

        int transferRet = av_hwframe_transfer_data(cpuFrame, frame, 0);
        av_frame_unref(frame);

        if (transferRet < 0) {
          av_frame_free(&cpuFrame);
          break;
        }

        int srcW = cpuFrame->width;
        int srcH = cpuFrame->height;

        // Ensure sws context matches (src → dst)
        if (!m_swsCtx || !m_rgbFrame || !m_rgbBuffer || m_srcWidth != srcW || m_srcHeight != srcH || m_width != dstW || m_height != dstH) {
          if (m_swsCtx) sws_freeContext(m_swsCtx);
          m_srcWidth = srcW; m_srcHeight = srcH;
          m_width = dstW; m_height = dstH;
          m_swsCtx = sws_getContext(
              srcW, srcH, (AVPixelFormat)cpuFrame->format, dstW, dstH,
              AV_PIX_FMT_RGBA, SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
          if (!m_swsCtx)
              m_swsCtx = sws_getContext(
                  srcW, srcH, (AVPixelFormat)cpuFrame->format, dstW, dstH,
                  AV_PIX_FMT_RGBA, SWS_BILINEAR, nullptr, nullptr, nullptr);
        }

        if (m_swsCtx) {
          // sws_scale writes DIRECTLY to dstBuffer — zero intermediate copies
          uint8_t* dstData[4] = { dstBuffer, nullptr, nullptr, nullptr };
          int dstLinesize[4] = { dstW * 4, 0, 0, 0 };
          sws_scale(m_swsCtx, (uint8_t const *const *)cpuFrame->data,
                    cpuFrame->linesize, 0, srcH, dstData, dstLinesize);
          success = true;
        }

        av_frame_free(&cpuFrame);
      } else {
        // SOFTWARE path — also direct write
        int srcW = frame->width;
        int srcH = frame->height;

        if (!m_swsCtx || !m_rgbFrame || !m_rgbBuffer || m_srcWidth != srcW || m_srcHeight != srcH || m_width != dstW || m_height != dstH) {
          if (m_swsCtx) sws_freeContext(m_swsCtx);
          m_srcWidth = srcW; m_srcHeight = srcH;
          m_width = dstW; m_height = dstH;
          m_swsCtx = sws_getContext(
              srcW, srcH, (AVPixelFormat)frame->format, dstW, dstH,
              AV_PIX_FMT_RGBA, SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
          if (!m_swsCtx)
              m_swsCtx = sws_getContext(
                  srcW, srcH, (AVPixelFormat)frame->format, dstW, dstH,
                  AV_PIX_FMT_RGBA, SWS_BILINEAR, nullptr, nullptr, nullptr);
        }

        if (m_swsCtx) {
          uint8_t* dstData[4] = { dstBuffer, nullptr, nullptr, nullptr };
          int dstLinesize[4] = { dstW * 4, 0, 0, 0 };
          sws_scale(m_swsCtx, (uint8_t const *const *)frame->data,
                    frame->linesize, 0, srcH, dstData, dstLinesize);
          success = true;
        }
      }

      m_lastDecodedFrame = current_frame_idx;

      auto decodeEnd = std::chrono::steady_clock::now();
      double decMs = std::chrono::duration_cast<std::chrono::microseconds>(decodeEnd - decodeStart).count() / 1000.0;
      std::cout << "[DECODE-D] OK frame=" << targetFrame << " dt=" << decMs << "ms\n" << std::flush;

      av_frame_free(&frame);
      break;

    } else if (response == AVERROR(EAGAIN)) {
      if (++retryCount > MAX_DECODE_RETRIES) break;
      if (av_read_frame(m_formatCtx, packet) >= 0) {
        if (packet->stream_index == m_videoStreamIndex)
          avcodec_send_packet(m_codecCtx, packet);
        av_packet_unref(packet);
      } else {
        avcodec_send_packet(m_codecCtx, nullptr);
      }
    } else {
      break;
    }
  }

  av_packet_free(&packet);
  if (!success) av_frame_free(&frame);
  return success;
}

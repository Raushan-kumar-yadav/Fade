#include "video/videoDecoder.hpp"
#include "core/api/Logger.hpp"
#include <cmath>

videoDecoder::videoDecoder(const std::string &filePath) : m_filepath(filePath) {
  m_lastDecodedFrame = -1;
  m_formatCtx = nullptr;

  if (avformat_open_input(&m_formatCtx, m_filepath.c_str(), nullptr, nullptr) !=
      0) {
    LOG_ERROR("FFmpeg: Could not open file " + m_filepath);
    return;
  }

  if (avformat_find_stream_info(m_formatCtx, nullptr) < 0) {
    LOG_ERROR("FFmpeg: Could not find stream info for " + m_filepath);
    return;
  }

  LOG_INFO("Format " + std::string(m_formatCtx->iformat->long_name) +
           ", duration " + std::to_string(m_formatCtx->duration) + " us");

  // Find the video stream
  for (unsigned int i = 0; i < m_formatCtx->nb_streams; i++) {

    AVCodecParameters *localCodecParam = m_formatCtx->streams[i]->codecpar;
    const AVCodec *localCodec = avcodec_find_decoder(localCodecParam->codec_id);

    if (localCodecParam->codec_type == AVMEDIA_TYPE_VIDEO) {

      AVStream *videoStream = m_formatCtx->streams[i];

      m_videoStreamIndex = i;
      m_width = localCodecParam->width;
      m_height = localCodecParam->height;
      m_duration = m_formatCtx->duration;
      m_videoCodex = localCodec;
      m_fps = av_q2d(videoStream->avg_frame_rate);
      m_timeBase = videoStream->time_base;
      m_codecCtx = avcodec_alloc_context3(localCodec);

      if (avcodec_parameters_to_context(m_codecCtx, localCodecParam) < 0) {
        LOG_ERROR("failed to copy codec parameter to decorder context");
        return;
      }

      m_codecCtx->thread_count = 0;
      m_codecCtx->thread_type = FF_THREAD_FRAME;

      if (avcodec_open2(m_codecCtx, m_videoCodex, nullptr) < 0) {
        LOG_ERROR("Faild to run the video codec");
        return;
      };

      m_swsCtx = nullptr; // built lazily on first frame
      m_rgbFrame = av_frame_alloc();
      int numBytes =
          av_image_get_buffer_size(AV_PIX_FMT_RGBA, m_width, m_height, 1);
      m_rgbBuffer = (uint8_t *)av_malloc(numBytes * sizeof(uint8_t));
      av_image_fill_arrays(m_rgbFrame->data, m_rgbFrame->linesize, m_rgbBuffer,
                           AV_PIX_FMT_RGBA, m_width, m_height, 1);

      LOG_INFO("Found Video! Dimensions: " + std::to_string(m_width) + "x" +
               std::to_string(m_height));
      break;

    } else if (localCodecParam->codec_type == AVMEDIA_TYPE_AUDIO) {
      LOG_INFO("Found Audio Stream at index " + std::to_string(i));
    }
  }

  m_packet = av_packet_alloc();
  m_frame = av_frame_alloc();
}

videoDecoder::~videoDecoder() {
  if (m_frame) {
    av_frame_free(&m_frame);
  }

  if (m_packet) {
    av_packet_free(&m_packet);
  }

  if (m_swsCtx) {
    sws_freeContext(m_swsCtx);
    m_swsCtx = nullptr;
  }
  if (m_rgbBuffer) {
    av_free(m_rgbBuffer);
    m_rgbBuffer = nullptr;
  }
  if (m_rgbFrame) {
    av_frame_free(&m_rgbFrame);
    m_rgbFrame = nullptr;
  }

  if (m_codecCtx) {
    avcodec_free_context(&m_codecCtx);
  }

  if (m_formatCtx) {
    avformat_close_input(&m_formatCtx);
  }

  LOG_INFO("Video Decoder cleanly destroyed. Memory freed.");
}

std::shared_ptr<DecodedFrame> videoDecoder::decodeFrame(int64_t frameNumber) {
  if (frameNumber != m_lastDecodedFrame + 1) {

    double timeInSecond = static_cast<double>(frameNumber) / m_fps;
    int64_t target_pts = std::round(timeInSecond / av_q2d(m_timeBase));

    av_seek_frame(m_formatCtx, m_videoStreamIndex, target_pts,
                  AVSEEK_FLAG_BACKWARD);
    avcodec_flush_buffers(m_codecCtx);

    m_lastDecodedFrame = -1;
  }

  while (true) {

    int response = avcodec_receive_frame(m_codecCtx, m_frame);

    if (response == 0) {

      // Skip frames with invalid pixel format — these appear right after
      // avcodec_flush_buffers() during seeks before the decoder re-settles.
      if (m_frame->format < 0 || m_frame->width <= 0 || m_frame->height <= 0) {
        av_frame_unref(m_frame);
        continue;
      }

      double timestamp_sec = m_frame->pts * av_q2d(m_timeBase);
      int64_t current_frame_idx = std::round(timestamp_sec * m_fps);

      if (current_frame_idx < frameNumber) {
        av_frame_unref(m_frame);
        continue;
      }

      // Rebuild sws context lazily if format or dimensions changed
      if (!m_swsCtx || m_lastSwsFmt != m_frame->format ||
          m_lastSwsW != m_frame->width || m_lastSwsH != m_frame->height) {
        if (m_swsCtx) {
          sws_freeContext(m_swsCtx);
          m_swsCtx = nullptr;
        }
        if (m_rgbBuffer) {
          av_free(m_rgbBuffer);
          m_rgbBuffer = nullptr;
        }
        if (m_rgbFrame) {
          av_frame_free(&m_rgbFrame);
          m_rgbFrame = nullptr;
        }
        int sw = m_frame->width > 0 ? m_frame->width : m_width;
        int sh = m_frame->height > 0 ? m_frame->height : m_height;
        m_swsCtx = sws_getContext(sw, sh, (AVPixelFormat)m_frame->format,
                                  sw, sh, AV_PIX_FMT_RGBA,
                                  SWS_FAST_BILINEAR, nullptr, nullptr, nullptr);
        if (!m_swsCtx) {
          LOG_ERROR("videoDecoder: sws_getContext failed fmt=" +
                    std::to_string(m_frame->format) +
                    " size=" + std::to_string(sw) + "x" + std::to_string(sh));
          av_frame_unref(m_frame);
          continue; // try next frame, not fatal
        }
        m_rgbFrame = av_frame_alloc();
        int numBytes = av_image_get_buffer_size(AV_PIX_FMT_RGBA, sw, sh, 1);
        m_rgbBuffer = (uint8_t *)av_malloc(numBytes);
        av_image_fill_arrays(m_rgbFrame->data, m_rgbFrame->linesize,
                             m_rgbBuffer, AV_PIX_FMT_RGBA, sw, sh, 1);
        m_lastSwsFmt = m_frame->format;
        m_lastSwsW   = sw;
        m_lastSwsH   = sh;
      }

      auto decordedFrame = std::make_shared<DecodedFrame>();
      decordedFrame->width = m_frame->width > 0 ? m_frame->width : m_width;
      decordedFrame->height = m_frame->height > 0 ? m_frame->height : m_height;
      decordedFrame->frameNumber = current_frame_idx;
      decordedFrame->pts = m_frame->pts;
      decordedFrame->type = FrameType::SOFTWARE_RGBA;
      decordedFrame->isStatic = false;

      if (m_swsCtx && m_rgbFrame && m_rgbBuffer) {
        sws_scale(m_swsCtx, (uint8_t const *const *)m_frame->data,
                  m_frame->linesize, 0, decordedFrame->height, m_rgbFrame->data,
                  m_rgbFrame->linesize);
        size_t totalBytes = static_cast<size_t>(decordedFrame->width) * decordedFrame->height * 4;
        decordedFrame->dataRGBA.resize(totalBytes);
        if (m_rgbFrame->linesize[0] == static_cast<int>(decordedFrame->width * 4)) {
          memcpy(decordedFrame->dataRGBA.data(), m_rgbFrame->data[0], totalBytes);
        } else {
          for (int y = 0; y < (int)decordedFrame->height; ++y) {
            memcpy(decordedFrame->dataRGBA.data() + y * decordedFrame->width * 4,
                   m_rgbFrame->data[0] + y * m_rgbFrame->linesize[0],
                   decordedFrame->width * 4);
          }
        }
      } else {
        LOG_ERROR("videoDecoder: swsCtx not initialized (fmt=" +
                  std::to_string(m_frame->format) + ")");
        av_frame_unref(m_frame);
        continue; // don't abort — try the next frame
      }

      decordedFrame->valid = true;
      m_lastDecodedFrame = current_frame_idx;

      return decordedFrame;
    }

    if (response == AVERROR_EOF)
      return nullptr;
    if (response != AVERROR(EAGAIN))
      return nullptr;

    if (av_read_frame(m_formatCtx, m_packet) >= 0) {
      if (m_packet->stream_index == m_videoStreamIndex) {
        avcodec_send_packet(m_codecCtx, m_packet);
      }
      av_packet_unref(m_packet);
    } else {
      avcodec_send_packet(m_codecCtx, nullptr);
    }
  }
}

int videoDecoder::getWidth() const { return m_width; }
int videoDecoder::getHeight() const { return m_height; }
double videoDecoder::getDuration() const { return m_duration; }
double videoDecoder::getFps() const { return m_fps; }

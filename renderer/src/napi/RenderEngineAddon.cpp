/**
 * RenderEngineAddon.cpp — Node.js NAPI addon entry point
 *
 * Exposes to JavaScript (Electron main process):
 *
 *   initialize(width, height, fps, effectsDir?, pythonPort?) → void
 *   seekFrame(frameNumber)                                   → void
 *   play()                                                   → void
 *   pause()                                                  → void
 *   isPlaying()                                              → bool
 *   getSharedBuffer()                                        → ArrayBuffer (zero-copy)
 *   setFrameReadyCallback(fn: (frameNum: number) => void)    → void
 *   getStats()                                               → { width, height, fps }
 *
 * Frame delivery pipeline:
 *   seekFrame(n)
 *     → HTTP GET http://127.0.0.1:{pythonPort}/render/frame/{n}
 *     → JSON → FrameDescriptor
 *     → HeadlessCompositor::renderFrame()
 *     → reads pixels → SharedArrayBuffer
 *     → fires JS callback: onFrameReady(n)
 */

#define NAPI_VERSION 8
#include <napi.h>

#include "../HeadlessCompositor.hpp"
#include "FrameDescriptor.hpp"

// Simple HTTP GET using WinHTTP (no extra lib needed on Windows)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <winhttp.h>
#pragma comment(lib, "winhttp.lib")

#include <atomic>
#include <functional>
#include <iostream>
#include <memory>
#include <string>
#include <thread>

// ── State ─────────────────────────────────────────────────────────────────────

namespace {

std::unique_ptr<HeadlessCompositor> g_compositor;
int  g_pythonPort      = 8001;
int  g_width           = 1920;
int  g_height          = 1080;
float g_fps            = 30.f;

// NAPI threadsafe function for firing JS callback
Napi::ThreadSafeFunction g_tsfn;
std::atomic<bool>        g_tsfnActive{false};

// ── WinHTTP GET helper ────────────────────────────────────────────────────────

std::string httpGet(const std::string& path) {
    std::string result;

    HINTERNET hSession = WinHttpOpen(L"FadeRenderEngine/1.0",
                                      WINHTTP_ACCESS_TYPE_NO_PROXY,
                                      WINHTTP_NO_PROXY_NAME,
                                      WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) return result;

    HINTERNET hConnect = WinHttpConnect(hSession, L"127.0.0.1",
                                         static_cast<INTERNET_PORT>(g_pythonPort), 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); return result; }

    std::wstring wpath(path.begin(), path.end());
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET",
                                             wpath.c_str(),
                                             nullptr,
                                             WINHTTP_NO_REFERER,
                                             WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
    if (!hRequest) { WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession); return result; }

    if (WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                            WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
        WinHttpReceiveResponse(hRequest, nullptr)) {
        DWORD size = 0;
        do {
            WinHttpQueryDataAvailable(hRequest, &size);
            if (size == 0) break;
            std::string buf(size, '\0');
            DWORD read = 0;
            WinHttpReadData(hRequest, buf.data(), size, &read);
            result.append(buf.data(), read);
        } while (size > 0);
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);
    return result;
}

// ── Frame rendering (called from seekFrame) ───────────────────────────────────

void renderFrameImpl(int64_t frameNum) {
    if (!g_compositor) return;

    // 1. Fetch frame descriptor from Python backend
    std::string json = httpGet("/render/frame/" + std::to_string(frameNum));
    if (json.empty()) {
        std::cerr << "[RenderEngine] Empty response from Python for frame " << frameNum << "\n";
        return;
    }

    // 2. Parse → FrameDescriptor
    FrameDescriptor fd = parseFrameDescriptor(json);
    if (!fd.valid) return;

    // 3. Composite on GPU, readback to SharedArrayBuffer
    g_compositor->renderFrame(fd);
    // Callback is fired from inside renderFrame → onFrameReady
}

} // namespace

// ── NAPI functions ─────────────────────────────────────────────────────────────

// initialize(width, height, fps, effectsDir?, pythonPort?)
Napi::Value Initialize(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();

    if (info.Length() < 3) {
        Napi::TypeError::New(env, "initialize(width, height, fps[, effectsDir[, pythonPort]])")
            .ThrowAsJavaScriptException();
        return env.Undefined();
    }

    g_width  = info[0].As<Napi::Number>().Int32Value();
    g_height = info[1].As<Napi::Number>().Int32Value();
    g_fps    = info[2].As<Napi::Number>().FloatValue();

    std::string effectsDir;
    if (info.Length() > 3 && info[3].IsString())
        effectsDir = info[3].As<Napi::String>().Utf8Value();

    if (info.Length() > 4 && info[4].IsNumber())
        g_pythonPort = info[4].As<Napi::Number>().Int32Value();

    try {
        g_compositor = std::make_unique<HeadlessCompositor>(g_width, g_height, g_fps, effectsDir);

        g_compositor->setPythonPort(g_pythonPort);

        // Wire up the frame-ready callback
        g_compositor->setFrameReadyCallback([](int64_t frameNum) {
            if (!g_tsfnActive.load()) return;
            auto* pFrame = new int64_t(frameNum);
            g_tsfn.NonBlockingCall(pFrame, [](Napi::Env env, Napi::Function jsCallback, int64_t* pf) {
                jsCallback.Call({Napi::Number::New(env, static_cast<double>(*pf))});
                delete pf;
            });
        });

        std::cout << "[RenderEngine] Initialized " << g_width << "x" << g_height
                  << " @ " << g_fps << "fps  pythonPort=" << g_pythonPort << "\n";
    } catch (const std::exception& e) {
        Napi::Error::New(env, std::string("RenderEngine init failed: ") + e.what())
            .ThrowAsJavaScriptException();
    }
    return env.Undefined();
}

// seekFrame(frameNumber: number) — seeks and renders one frame
Napi::Value SeekFrame(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();
    if (info.Length() < 1 || !info[0].IsNumber()) {
        Napi::TypeError::New(env, "seekFrame(frameNumber)").ThrowAsJavaScriptException();
        return env.Undefined();
    }
    int64_t frame = static_cast<int64_t>(info[0].As<Napi::Number>().Int64Value());
    if (g_compositor) g_compositor->seek(frame);
    return env.Undefined();
}

// play()
Napi::Value Play(const Napi::CallbackInfo& info) {
    if (g_compositor) g_compositor->play();
    return info.Env().Undefined();
}

// pause()
Napi::Value Pause(const Napi::CallbackInfo& info) {
    if (g_compositor) g_compositor->pause();
    return info.Env().Undefined();
}

// isPlaying() → boolean
Napi::Value IsPlaying(const Napi::CallbackInfo& info) {
    return Napi::Boolean::New(info.Env(),
           g_compositor ? g_compositor->isPlaying() : false);
}

// getSharedBuffer() — returns a Buffer COPY of the current frame pixels.
// Buffer::Copy is serializable over Electron IPC (unlike external ArrayBuffer).
Napi::Value GetSharedBuffer(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();
    if (!g_compositor) return env.Null();
    return Napi::Buffer<uint8_t>::Copy(
        env,
        g_compositor->getBuffer(),
        g_compositor->getBufferSize()
    );
}

// setFrameReadyCallback(fn: (frameNum: number) => void)
Napi::Value SetFrameReadyCallback(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();
    if (info.Length() < 1 || !info[0].IsFunction()) {
        Napi::TypeError::New(env, "setFrameReadyCallback(fn)").ThrowAsJavaScriptException();
        return env.Undefined();
    }

    if (g_tsfnActive.load()) {
        g_tsfn.Release();
        g_tsfnActive.store(false);
    }

    g_tsfn = Napi::ThreadSafeFunction::New(
        env,
        info[0].As<Napi::Function>(),
        "FrameReadyCallback",
        0,   // max queue size (0 = unlimited)
        1    // initial thread count
    );
    g_tsfnActive.store(true);

    return env.Undefined();
}

// getStats() → { width, height, fps, bufferSize }
Napi::Value GetStats(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();
    auto obj = Napi::Object::New(env);
    obj.Set("width",      Napi::Number::New(env, g_width));
    obj.Set("height",     Napi::Number::New(env, g_height));
    obj.Set("fps",        Napi::Number::New(env, g_fps));
    obj.Set("bufferSize", Napi::Number::New(env,
            g_compositor ? static_cast<double>(g_compositor->getBufferSize()) : 0));
    return obj;
}

// ── Addon registration ────────────────────────────────────────────────────────

Napi::Object Init(Napi::Env env, Napi::Object exports) {
    exports.Set("initialize",            Napi::Function::New(env, Initialize));
    exports.Set("seekFrame",             Napi::Function::New(env, SeekFrame));
    exports.Set("play",                  Napi::Function::New(env, Play));
    exports.Set("pause",                 Napi::Function::New(env, Pause));
    exports.Set("isPlaying",             Napi::Function::New(env, IsPlaying));
    exports.Set("getSharedBuffer",       Napi::Function::New(env, GetSharedBuffer));
    exports.Set("setFrameReadyCallback", Napi::Function::New(env, SetFrameReadyCallback));
    exports.Set("getStats",              Napi::Function::New(env, GetStats));
    return exports;
}

NODE_API_MODULE(render_engine, Init)

#pragma once
#include <iostream>
#include <string>

#ifndef LOG_INFO
#define LOG_INFO(m) std::cout << "[FADE] " << m << "\n"
#endif

#ifndef LOG_ERROR
#define LOG_ERROR(m) std::cerr << "[FADE ERR] " << m << "\n"
#endif

#ifndef LOG_WARN
#define LOG_WARN(m) std::cerr << "[FADE WARN] " << m << "\n"
#endif

#ifndef LOG_DEBUG
#define LOG_DEBUG(m) std::cout << "[FADE DBG] " << m << "\n"
#endif


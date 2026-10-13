#pragma once

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX

#pragma warning(push)
// CommonLib models engine layouts with intentional MSVC extensions.
#pragma warning(disable: 4200 4201)
#include <RE/Skyrim.h>
#include <REL/Relocation.h>
#include <SKSE/SKSE.h>

#include <fstream>

#ifdef NDEBUG
#include <spdlog/sinks/basic_file_sink.h>
#else
#include <spdlog/sinks/msvc_sink.h>
#endif
#pragma warning(pop)

// xbyak
#include <xbyak/xbyak.h>

using namespace std::literals;
using namespace REL::literals;

namespace logger = SKSE::log;

namespace stl 
{
	using namespace SKSE::stl;
}

namespace util 
{
	using SKSE::stl::report_and_fail;
}

#define DLLEXPORT __declspec(dllexport)

#define RELOCATION_OFFSET(SE, AE) REL::VariantOffset(SE, AE, 0).offset()

#include "plugin.h"
// The pinned framework has known declaration, enum and UTF conversion diagnostics.
#pragma warning(push)
#pragma warning(disable: 4099 4996 5054)
#include "SKSEMenuFramework.h"
#pragma warning(pop)
#include "HelperFunctions.h"
// Windows GDI defines a macro that collides with CommonLib methods.
#ifdef GetObject
#undef GetObject
#endif

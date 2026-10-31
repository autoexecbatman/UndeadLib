# UndeadLib: header-only C++20 grid algorithms (undead_core) and the C API
# over them (undead_c, a shared library the language bindings load).
#
# Configure and test, from the repository root:
#   cmake -S . -B build -G "Visual Studio 18 2026"
#       -DCMAKE_TOOLCHAIN_FILE=E:/dev/vcpkg/scripts/buildsystems/vcpkg.cmake
#   cmake --build build --config Debug
#   ctest --test-dir build -C Debug --output-on-failure
cmake_minimum_required(VERSION 3.25)

project(UndeadLib LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Every executable and DLL lands in one folder, so the tests find undead_c.dll.
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# Warnings are errors. /w14062 turns on the missing-enumerator warning that
# /W4 leaves off on MSVC.
function(undead_strict_warnings target)
	if(MSVC)
		target_compile_options(${target} PRIVATE /W4 /WX /permissive- /w14062 /utf-8)
	else()
		target_compile_options(${target} PRIVATE -Wall -Wextra -Wshadow -Werror)
	endif()
endfunction()

add_library(undead_core INTERFACE)
target_include_directories(undead_core INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(undead_core INTERFACE cxx_std_20)

# The dungeon demo: monsters chasing the player down a Dijkstra map.
add_executable(dungeon_demo demo/dungeon_demo.cpp demo/DungeonDemo.h)
target_link_libraries(dungeon_demo PRIVATE undead_core)
undead_strict_warnings(dungeon_demo)

if(EMSCRIPTEN)
	# The WebAssembly build: the C API as an ES module, undead_wasm.mjs and
	# undead_wasm.wasm, for the JavaScript binding. Configure it in its own
	# folder with emcmake, as the JavaScript section of CLAUDE.md shows.
	include(cmake/UndeadWasm.cmake)
	return()
endif()

add_library(undead_c SHARED
	src/undead_c.cpp
	include/undead/undead.h
)
target_link_libraries(undead_c PRIVATE undead_core)
target_include_directories(undead_c PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_definitions(undead_c PRIVATE UNDEAD_BUILDING_DLL)
undead_strict_warnings(undead_c)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

# The API documentation: build/docs/api.html, from the headers and the Python
# binding. It fails when a public declaration has no comment.
add_custom_target(docs
	COMMAND ${Python3_EXECUTABLE} -X utf8
		${CMAKE_CURRENT_SOURCE_DIR}/docs/api_page.py
		--root ${CMAKE_CURRENT_SOURCE_DIR}
		--out ${CMAKE_BINARY_DIR}/docs/api.html
	COMMENT "Writing ${CMAKE_BINARY_DIR}/docs/api.html"
	VERBATIM
)

option(UNDEAD_BUILD_TESTS "Build the UndeadLib test executable" ON)
if(UNDEAD_BUILD_TESTS)
	enable_testing()
	add_subdirectory(tests)

	# Plugin autoload is off for every pytest suite: none needs a plugin, and
	# a broken third-party one then cannot stop a suite loading.

	# The documentation generator's own tests, and its coverage gate.
	add_test(
		NAME docs_generator
		COMMAND ${Python3_EXECUTABLE} -m pytest -q -p no:cacheprovider
		WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/docs
	)
	set_tests_properties(docs_generator PROPERTIES
		ENVIRONMENT "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"
	)
	add_test(
		NAME docs_coverage
		COMMAND ${Python3_EXECUTABLE} -X utf8
			${CMAKE_CURRENT_SOURCE_DIR}/docs/api_page.py
			--root ${CMAKE_CURRENT_SOURCE_DIR} --check
	)

	# The demo runs to the end: every monster beside the player, exit 0.
	add_test(NAME dungeon_demo_runs COMMAND dungeon_demo)

	# The Python binding's suite, against the undead_c this build produced.
	add_test(
		NAME python_binding
		COMMAND ${Python3_EXECUTABLE} -m pytest -q -p no:cacheprovider
		WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/python
	)
	set_tests_properties(python_binding PROPERTIES
		ENVIRONMENT "UNDEAD_C_DLL=$<TARGET_FILE:undead_c>;PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"
	)

	# The C# binding's suite against the same undead_c, and its format gate.
	find_program(UNDEAD_DOTNET dotnet REQUIRED)
	add_test(
		NAME csharp_binding
		COMMAND ${UNDEAD_DOTNET} test Undead.Tests -c Release
		WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/csharp
	)
	set_tests_properties(csharp_binding PROPERTIES
		ENVIRONMENT "UNDEAD_C_DLL=$<TARGET_FILE:undead_c>"
	)
	add_test(
		NAME csharp_format
		COMMAND ${UNDEAD_DOTNET} format Undead.Tests/Undead.Tests.csproj --verify-no-changes
		WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/csharp
	)
endif()

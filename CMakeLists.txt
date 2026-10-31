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

add_library(undead_c SHARED
	src/undead_c.cpp
	include/undead/undead.h
)
target_link_libraries(undead_c PRIVATE undead_core)
target_include_directories(undead_c PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_definitions(undead_c PRIVATE UNDEAD_BUILDING_DLL)
undead_strict_warnings(undead_c)

option(UNDEAD_BUILD_TESTS "Build the UndeadLib test executable" ON)
if(UNDEAD_BUILD_TESTS)
	enable_testing()
	add_subdirectory(tests)

	# The Python binding's suite, against the undead_c this build produced.
	# Plugin autoload is off: the suite needs none, and a broken third-party
	# plugin then cannot stop it loading.
	find_package(Python3 REQUIRED COMPONENTS Interpreter)
	add_test(
		NAME python_binding
		COMMAND ${Python3_EXECUTABLE} -m pytest -q -p no:cacheprovider
		WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/python
	)
	set_tests_properties(python_binding PROPERTIES
		ENVIRONMENT "UNDEAD_C_DLL=$<TARGET_FILE:undead_c>;PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"
	)
endif()

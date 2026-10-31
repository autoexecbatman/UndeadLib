# The WebAssembly half of the build, included from CMakeLists.txt when the
# toolchain is Emscripten. It builds the C API as an ES module for the
# JavaScript binding and tests both it and the dungeon demo under Node.
#
# Configure and test, from the repository root, after emsdk_env:
#   emcmake <cmake> -S . -B build-wasm -G Ninja -DCMAKE_BUILD_TYPE=Release
#   <cmake> --build build-wasm
#   <ctest> --test-dir build-wasm --output-on-failure

# C++ exceptions compile to wasm exceptions, so the C API catches the core's.
add_executable(undead_wasm src/undead_c.cpp include/undead/undead.h)
target_link_libraries(undead_wasm PRIVATE undead_core)
undead_strict_warnings(undead_wasm)
target_compile_options(undead_wasm PRIVATE -fwasm-exceptions)
target_link_options(undead_wasm PRIVATE
	-fwasm-exceptions
	-sMODULARIZE=1
	-sEXPORT_ES6=1
	"-sENVIRONMENT=web,node"
	-sALLOW_MEMORY_GROWTH=1
	"-sEXPORTED_FUNCTIONS=_undead_dijkstra_map,_malloc,_free"
	"-sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32"
)
set_target_properties(undead_wasm PROPERTIES SUFFIX ".mjs")

option(UNDEAD_BUILD_TESTS "Build and register the UndeadLib tests" ON)
if(UNDEAD_BUILD_TESTS)
	enable_testing()
	find_program(UNDEAD_NODE node REQUIRED)

	# The demo, compiled for wasm32 and run under Node through the
	# toolchain's emulator: the core itself on a 32-bit size_t.
	add_test(NAME dungeon_demo_runs COMMAND dungeon_demo)

	# The JavaScript binding's suite, against the module this build produced.
	add_test(
		NAME js_binding
		COMMAND ${UNDEAD_NODE} --test
		WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings/js
	)
	set_tests_properties(js_binding PROPERTIES
		ENVIRONMENT "UNDEAD_JS_MODULE=$<TARGET_FILE:undead_wasm>"
	)
endif()

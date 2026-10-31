# undead_tests: one GTest executable covering the C++ core and the C API.
# CApiCaller.c is compiled as C, which is the check that undead.h is valid C.
find_package(GTest CONFIG REQUIRED)

add_executable(undead_tests
	BellmanFordOracle.h
	CApiCaller.c
	CApiTest.cpp
	DialSearchTest.cpp
	DungeonDemoTest.cpp
	GridGraphTest.cpp
	test_main.cpp
)
target_link_libraries(undead_tests PRIVATE
	undead_core
	undead_c
	GTest::gtest
)
undead_strict_warnings(undead_tests)
# The demo's game rules are tested from its header.
target_include_directories(undead_tests PRIVATE ${PROJECT_SOURCE_DIR}/demo)

include(GoogleTest)
gtest_discover_tests(undead_tests DISCOVERY_MODE PRE_TEST)

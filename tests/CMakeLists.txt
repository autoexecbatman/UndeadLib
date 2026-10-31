# undead_tests: one GTest executable covering the C++ core and the C API.
# CApiCaller.c is compiled as C, which is the check that undead.h is valid C.
find_package(GTest CONFIG REQUIRED)

add_executable(undead_tests
	BellmanFordOracle.h
	CApiCaller.c
	CApiTest.cpp
	DialSearchTest.cpp
	GridGraphTest.cpp
	test_main.cpp
)
target_link_libraries(undead_tests PRIVATE
	undead_core
	undead_c
	GTest::gtest
)
undead_strict_warnings(undead_tests)

include(GoogleTest)
gtest_discover_tests(undead_tests DISCOVERY_MODE PRE_TEST)

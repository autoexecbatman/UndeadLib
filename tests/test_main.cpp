// The GTest entry point. Under MSVC it sends CRT assertion and error reports,
// such as a Debug build's out-of-range vector index, to stderr instead of a
// modal dialog, so an unattended run fails rather than waits for a click.
#if defined(_MSC_VER)
#include <crtdbg.h>
#endif

#include <gtest/gtest.h>

int main(int argc, char** argv)
{
#if defined(_MSC_VER)
	_CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);
	_CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);
	_CrtSetReportMode(_CRT_ERROR, _CRTDBG_MODE_FILE);
	_CrtSetReportFile(_CRT_ERROR, _CRTDBG_FILE_STDERR);
#endif
	testing::InitGoogleTest(&argc, argv);
	return RUN_ALL_TESTS();
}

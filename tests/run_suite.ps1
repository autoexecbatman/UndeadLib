# Builds undead_tests in one configuration and runs it, for mutate.py.
#
# Usage, from anywhere:
#   powershell -NoProfile -File tests/run_suite.ps1 Debug "*-*Uint32Max*:*DistanceOverflow*"
#   powershell -NoProfile -File tests/run_suite.ps1 Release "*Uint32Max*:*DistanceOverflow*"
# The second argument is a GTest filter. Exit 0 when every selected test
# passes; 3 with "BUILD FAILED" when the mutant did not compile, which
# mutate.py would otherwise score as caught.
param(
	[Parameter(Mandatory = $true)][string]$Configuration,
	[Parameter(Mandatory = $true)][string]$Filter
)

$root = Split-Path -Parent $PSScriptRoot
$cmake = "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"

& $cmake --build "$root\build" --config $Configuration --target undead_tests | Out-Null
if ($LASTEXITCODE -ne 0)
{
	Write-Output "BUILD FAILED"
	exit 3
}

& "$root\build\bin\$Configuration\undead_tests.exe" "--gtest_filter=$Filter" --gtest_brief=1
exit $LASTEXITCODE

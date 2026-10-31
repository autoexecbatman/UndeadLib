using System;
using System.IO;
using System.Linq;

using Xunit;

namespace Undead.Tests;

/// <summary>
/// Loads the undead_c.dll named by UNDEAD_C_DLL once for every test in a class.
/// </summary>
public sealed class LibraryFixture : IDisposable
{
	/// <summary>Creates the fixture, loading the DLL under test.</summary>
	public LibraryFixture()
	{
		DllPath = Environment.GetEnvironmentVariable("UNDEAD_C_DLL")
			?? throw new InvalidOperationException("UNDEAD_C_DLL must name the undead_c.dll under test");
		Library = new UndeadLibrary(DllPath);
	}

	/// <summary>The path the library was loaded from.</summary>
	public string DllPath { get; }

	/// <summary>The loaded library.</summary>
	public UndeadLibrary Library { get; }

	/// <summary>Unloads the library.</summary>
	public void Dispose()
	{
		Library.Dispose();
	}
}

/// <summary>
/// UndeadLibrary.DijkstraMap against hand-worked answers and a Bellman-Ford oracle,
/// every refusal made before C, every reachable C status, and the library's lifetime.
/// </summary>
public sealed class DijkstraMapTests : IClassFixture<LibraryFixture>
{
	private readonly LibraryFixture fixture;

	/// <summary>Receives the shared library.</summary>
	/// <param name="fixture">The loaded DLL.</param>
	public DijkstraMapTests(LibraryFixture fixture)
	{
		this.fixture = fixture;
	}

	private UndeadLibrary Library => fixture.Library;

	/// <summary>
	/// Shortest distances by relaxing every grid edge until nothing changes;
	/// neighbours are enumerated here by offset, not by the library.
	/// </summary>
	private static uint?[] BellmanFord(int width, int height, byte[] costs, bool isEightWay, int[] sources)
	{
		var distances = new uint?[width * height];
		foreach (int source in sources)
		{
			distances[source] = 0;
		}
		bool isChanged = true;
		while (isChanged)
		{
			isChanged = false;
			for (int row = 0; row < height; ++row)
			{
				for (int column = 0; column < width; ++column)
				{
					uint? here = distances[row * width + column];
					if (here is null)
					{
						continue;
					}
					for (int rowOffset = -1; rowOffset <= 1; ++rowOffset)
					{
						for (int columnOffset = -1; columnOffset <= 1; ++columnOffset)
						{
							bool isSelf = rowOffset == 0 && columnOffset == 0;
							bool isDiagonal = rowOffset != 0 && columnOffset != 0;
							int nextRow = row + rowOffset;
							int nextColumn = column + columnOffset;
							if (isSelf || (isDiagonal && !isEightWay))
							{
								continue;
							}
							if (nextRow < 0 || nextColumn < 0 || nextRow >= height || nextColumn >= width)
							{
								continue;
							}
							int target = nextRow * width + nextColumn;
							if (costs[target] == 0)
							{
								continue;
							}
							uint candidate = here.Value + costs[target];
							if (distances[target] is null || candidate < distances[target])
							{
								distances[target] = candidate;
								isChanged = true;
							}
						}
					}
				}
			}
		}
		return distances;
	}

	[Fact]
	public void DoorCorridorCostsTwoToEnterTheDoor()
	{
		byte[] costs = [1, 1, 1, 1, 2, 1, 1];
		Assert.Equal(
			new uint?[] { 0, 1, 2, 3, 5, 6, 7 },
			Library.DijkstraMap(7, 1, costs, Connectivity.EightWay, [0]));
	}

	[Fact]
	public void WallLeavesTheFarSideNull()
	{
		byte[] costs = [1, 0, 1];
		Assert.Equal(
			new uint?[] { 0, null, null },
			Library.DijkstraMap(3, 1, costs, Connectivity.FourWay, [0]));
	}

	[Fact]
	public void EightWayCutsTheCornerFourWayWalks()
	{
		byte[] room = [1, 1, 1, 1, 1, 1, 1, 1, 1];
		Assert.Equal(4u, Library.DijkstraMap(3, 3, room, Connectivity.FourWay, [0])[8]);
		Assert.Equal(2u, Library.DijkstraMap(3, 3, room, Connectivity.EightWay, [0])[8]);
	}

	[Fact]
	public void NoSourcesLeavesEveryCellNull()
	{
		byte[] costs = [1, 1];
		Assert.Equal(
			new uint?[] { null, null },
			Library.DijkstraMap(2, 1, costs, Connectivity.FourWay, []));
	}

	[Fact]
	public void EmptyGridReturnsNoDistances()
	{
		Assert.Empty(Library.DijkstraMap(0, 4, [], Connectivity.FourWay, []));
	}

	[Fact]
	public void RandomGridsAgreeWithBellmanFord()
	{
		for (int seed = 1; seed <= 100; ++seed)
		{
			// A seeded System.Random repeats its sequence exactly.
			var random = new Random(seed);
			int width = random.Next(1, 13);
			int height = random.Next(1, 13);
			var costs = new byte[width * height];
			random.NextBytes(costs);
			int[] sources = [random.Next(costs.Length), random.Next(costs.Length)];
			foreach (bool isEightWay in new[] { false, true })
			{
				Connectivity connectivity = isEightWay ? Connectivity.EightWay : Connectivity.FourWay;
				uint?[] expected = BellmanFord(width, height, costs, isEightWay, sources);
				uint?[] actual = Library.DijkstraMap(width, height, costs, connectivity, sources);
				Assert.True(expected.SequenceEqual(actual), $"seed {seed}, eight-way {isEightWay}");
			}
		}
	}

	[Fact]
	public void NegativeWidthIsRefusedBeforeC()
	{
		// With height 0 the empty costs match, so only the width check refuses.
		var error = Assert.Throws<ArgumentOutOfRangeException>(
			() => Library.DijkstraMap(-1, 0, [], Connectivity.FourWay, []));
		Assert.Equal("width", error.ParamName);
	}

	[Fact]
	public void NegativeHeightIsRefusedBeforeC()
	{
		var error = Assert.Throws<ArgumentOutOfRangeException>(
			() => Library.DijkstraMap(0, -1, [], Connectivity.FourWay, []));
		Assert.Equal("height", error.ParamName);
	}

	[Fact]
	public void NegativeSourceIsRefusedBeforeC()
	{
		// C would refuse it too, as a huge index; the message tells the two apart.
		byte[] costs = [1, 1];
		var error = Assert.Throws<ArgumentOutOfRangeException>(
			() => Library.DijkstraMap(2, 1, costs, Connectivity.FourWay, [0, -1]));
		Assert.Equal("sources", error.ParamName);
		Assert.DoesNotContain("UNDEAD_ERROR", error.Message, StringComparison.Ordinal);
	}

	[Fact]
	public void CostsOfTheWrongLengthAreRefusedShortOrLong()
	{
		var shortCosts = new byte[7];
		var longCosts = new byte[10];
		Assert.Equal("stepCosts", Assert.Throws<ArgumentException>(
			() => Library.DijkstraMap(3, 3, shortCosts, Connectivity.FourWay, [0])).ParamName);
		Assert.Equal("stepCosts", Assert.Throws<ArgumentException>(
			() => Library.DijkstraMap(3, 3, longCosts, Connectivity.FourWay, [0])).ParamName);
	}

	[Fact]
	public void CellCountIsComputedWithoutWrapping()
	{
		// 65536 * 65536 wraps to 0 in int, which would match empty costs and
		// send C a four-billion-cell grid with nothing behind the pointer.
		var error = Assert.Throws<ArgumentException>(
			() => Library.DijkstraMap(65536, 65536, [], Connectivity.FourWay, []));
		Assert.Equal("stepCosts", error.ParamName);
	}

	[Fact]
	public void SourceOutsideTheGridIsRefusedByC()
	{
		var costs = new byte[] { 1, 1, 1, 1, 1, 1, 1 };
		var error = Assert.Throws<ArgumentOutOfRangeException>(
			() => Library.DijkstraMap(7, 1, costs, Connectivity.FourWay, [7]));
		Assert.Contains("UNDEAD_ERROR_SOURCE_OUT_OF_RANGE", error.Message, StringComparison.Ordinal);
	}

	[Fact]
	public void UnknownConnectivityIsRefusedByC()
	{
		byte[] costs = [1, 1];
		var error = Assert.Throws<ArgumentException>(
			() => Library.DijkstraMap(2, 1, costs, (Connectivity)6, [0]));
		Assert.Contains("UNDEAD_ERROR_CONNECTIVITY", error.Message, StringComparison.Ordinal);
	}

	[Fact]
	public void DistanceReachingUint32MaxIsRefusedByC()
	{
		// Cost-255 corridor: cell 16843009 is the first at 4294967295.
		var costs = new byte[16843010];
		Array.Fill(costs, (byte)255);
		var error = Assert.Throws<OverflowException>(
			() => Library.DijkstraMap(costs.Length, 1, costs, Connectivity.FourWay, [0]));
		Assert.Contains("UNDEAD_ERROR_DISTANCE_OVERFLOW", error.Message, StringComparison.Ordinal);
	}

	[Theory]
	[InlineData(1, typeof(InvalidOperationException), "UNDEAD_ERROR_NULL_ARGUMENT")]
	[InlineData(2, typeof(ArgumentException), "UNDEAD_ERROR_GRID_SIZE")]
	[InlineData(3, typeof(ArgumentOutOfRangeException), "UNDEAD_ERROR_SOURCE_OUT_OF_RANGE")]
	[InlineData(4, typeof(ArgumentException), "UNDEAD_ERROR_CONNECTIVITY")]
	[InlineData(5, typeof(OverflowException), "UNDEAD_ERROR_DISTANCE_OVERFLOW")]
	[InlineData(6, typeof(InsufficientMemoryException), "UNDEAD_ERROR_OUT_OF_MEMORY")]
	[InlineData(7, typeof(InvalidOperationException), "UNDEAD_ERROR_INTERNAL")]
	[InlineData(99, typeof(InvalidOperationException), "99")]
	public void EveryStatusMapsToItsException(int status, Type expectedType, string expectedName)
	{
		// The table in docs/csharp-binding-contract.md, including statuses no call here can reach.
		Exception error = UndeadLibrary.StatusException(status);
		Assert.Equal(expectedType, error.GetType());
		Assert.Contains(expectedName, error.Message, StringComparison.Ordinal);
	}

	[Fact]
	public void CallAfterDisposeIsRefused()
	{
		var library = new UndeadLibrary(fixture.DllPath);
		library.Dispose();
		byte[] costs = [1];
		Assert.Throws<ObjectDisposedException>(
			() => library.DijkstraMap(1, 1, costs, Connectivity.FourWay, [0]));
	}

	[Fact]
	public void TwoInstancesAreIndependent()
	{
		var first = new UndeadLibrary(fixture.DllPath);
		using var second = new UndeadLibrary(fixture.DllPath);
		first.Dispose();
		byte[] costs = [1, 1];
		Assert.Equal(new uint?[] { 0, 1 }, second.DijkstraMap(2, 1, costs, Connectivity.FourWay, [0]));
	}

	/// <summary>
	/// Copies a DLL into a fresh temporary folder, so deleting the copy shows whether it is
	/// still loaded: Windows refuses to delete a loaded DLL.
	/// </summary>
	private static string CopyToTemporaryFolder(string dllPath)
	{
		string folder = Path.Combine(Path.GetTempPath(), $"undead-{Guid.NewGuid():N}");
		Directory.CreateDirectory(folder);
		string copy = Path.Combine(folder, Path.GetFileName(dllPath));
		File.Copy(dllPath, copy);
		return copy;
	}

	[Fact]
	public void DisposeUnloadsTheDll()
	{
		string copy = CopyToTemporaryFolder(fixture.DllPath);
		var library = new UndeadLibrary(copy);
		Assert.Throws<UnauthorizedAccessException>(() => File.Delete(copy));
		library.Dispose();
		File.Delete(copy);
		Assert.False(File.Exists(copy));
		Directory.Delete(Path.GetDirectoryName(copy)!);
	}

	[Fact]
	public void DllWithoutTheExportIsRefusedAndUnloaded()
	{
		// gtest.dll is built beside undead_c.dll and has no undead_dijkstra_map.
		string gtest = Path.Combine(Path.GetDirectoryName(fixture.DllPath)!, "gtest.dll");
		Assert.True(File.Exists(gtest), $"{gtest} is the DLL without the export this test loads");
		string copy = CopyToTemporaryFolder(gtest);
		Assert.Throws<EntryPointNotFoundException>(() => new UndeadLibrary(copy));
		File.Delete(copy);
		Assert.False(File.Exists(copy));
		Directory.Delete(Path.GetDirectoryName(copy)!);
	}

	[Fact]
	public void MissingDllIsRefusedAtConstruction()
	{
		Assert.Throws<DllNotFoundException>(() => new UndeadLibrary("D:/no/such/undead_c.dll"));
	}
}

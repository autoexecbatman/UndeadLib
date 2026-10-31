// UndeadLibrary: the C API in undead_c.dll, loaded from a path the caller names.
// The class's example shows a call and each kind of refusal; the contract is
// docs/csharp-binding-contract.md.

using System;
using System.Runtime.InteropServices;

namespace Undead;

/// <summary>
/// The C API in undead_c.dll, loaded from a path the caller names and called through an
/// unmanaged function pointer. Contract: docs/csharp-binding-contract.md.
/// </summary>
/// <example>
/// <code>
/// using var library = new UndeadLibrary("build/bin/Release/undead_c.dll");
///
/// // A corridor of seven cells; the door at cell 4 costs 2 to enter.
/// byte[] costs = [1, 1, 1, 1, 2, 1, 1];
/// library.DijkstraMap(7, 1, costs, Connectivity.EightWay, [0]);
/// // -> { 0, 1, 2, 3, 5, 6, 7 }     cost 0 is a wall; unreached cells are null
///
/// library.DijkstraMap(7, 1, costs, Connectivity.EightWay, [7]);
/// // throws ArgumentOutOfRangeException: undead_dijkstra_map returned UNDEAD_ERROR_SOURCE_OUT_OF_RANGE
/// new UndeadLibrary("missing.dll");
/// // throws DllNotFoundException
/// </code>
/// </example>
public sealed unsafe class UndeadLibrary : IDisposable
{
	/// <summary>UNDEAD_UNREACHED: the distance C writes for a cell no source reaches.</summary>
	private const uint Unreached = uint.MaxValue;

	/// <summary>The C status names, indexed by status code, as undead.h numbers them.</summary>
	private static readonly string[] StatusNames =
	[
		"UNDEAD_OK",
		"UNDEAD_ERROR_NULL_ARGUMENT",
		"UNDEAD_ERROR_GRID_SIZE",
		"UNDEAD_ERROR_SOURCE_OUT_OF_RANGE",
		"UNDEAD_ERROR_CONNECTIVITY",
		"UNDEAD_ERROR_DISTANCE_OVERFLOW",
		"UNDEAD_ERROR_OUT_OF_MEMORY",
		"UNDEAD_ERROR_INTERNAL",
	];

	/// <summary>The loaded DLL; freed by Dispose.</summary>
	private readonly nint libraryHandle;

	/// <summary>undead_dijkstra_map, with the signature undead.h declares.</summary>
	private readonly delegate* unmanaged[Cdecl]<nuint, nuint, byte*, int, nuint*, nuint, uint*, int> dijkstraMap;

	/// <summary>Set by Dispose; every call checks it before touching the DLL.</summary>
	private bool isDisposed;

	/// <summary>Loads undead_c.dll from dllPath and finds its export.</summary>
	/// <example>
	/// <code>
	/// using var library = new UndeadLibrary("D:/repo/UndeadLib/build/bin/Release/undead_c.dll");
	/// </code>
	/// </example>
	/// <param name="dllPath">The DLL to load; a relative path is resolved by the OS loader.</param>
	/// <exception cref="ArgumentNullException">If dllPath is null.</exception>
	/// <exception cref="DllNotFoundException">If nothing loads from dllPath.</exception>
	/// <exception cref="EntryPointNotFoundException">If the DLL has no undead_dijkstra_map.</exception>
	public UndeadLibrary(string dllPath)
	{
		ArgumentNullException.ThrowIfNull(dllPath);
		libraryHandle = NativeLibrary.Load(dllPath);
		try
		{
			nint export = NativeLibrary.GetExport(libraryHandle, "undead_dijkstra_map");
			dijkstraMap = (delegate* unmanaged[Cdecl]<nuint, nuint, byte*, int, nuint*, nuint, uint*, int>)export;
		}
		catch
		{
			// A DLL without the export is not kept loaded.
			NativeLibrary.Free(libraryHandle);
			throw;
		}
	}

	/// <summary>
	/// Distance from the nearest source to every cell, by Dijkstra's algorithm in C. A cell's
	/// cost is paid to enter it, and cost 0 is a wall. Arguments C would misread are refused
	/// here; the rest is refused by C, and its status becomes the exception.
	/// </summary>
	/// <example>
	/// <code>
	/// byte[] room = [1, 1, 1, 1, 1, 1, 1, 1, 1];                       // 3 x 3, all floor
	/// library.DijkstraMap(3, 3, room, Connectivity.FourWay, [0])[8];   // -> 4
	/// library.DijkstraMap(3, 3, room, Connectivity.EightWay, [0])[8];  // -> 2
	/// library.DijkstraMap(-1, 0, [], Connectivity.FourWay, []);
	/// // throws ArgumentOutOfRangeException, ParamName "width"
	/// </code>
	/// </example>
	/// <param name="width">Cells per row.</param>
	/// <param name="height">Rows.</param>
	/// <param name="stepCosts">width * height costs, indexed row * width + column.</param>
	/// <param name="connectivity">Which neighbours a cell has; an undefined value is refused by C.</param>
	/// <param name="sources">Cell indices at distance 0.</param>
	/// <returns>One distance per cell, null where no source reaches.</returns>
	/// <exception cref="ObjectDisposedException">If the library was disposed.</exception>
	/// <exception cref="ArgumentOutOfRangeException">
	/// If width, height or a source is negative, or C finds a source outside the grid.
	/// </exception>
	/// <exception cref="ArgumentException">
	/// If stepCosts is not width * height long, or C refuses the connectivity.
	/// </exception>
	/// <exception cref="OverflowException">If a distance would reach UINT32_MAX.</exception>
	public uint?[] DijkstraMap(
		int width,
		int height,
		ReadOnlySpan<byte> stepCosts,
		Connectivity connectivity,
		ReadOnlySpan<int> sources)
	{
		ObjectDisposedException.ThrowIf(isDisposed, this);
		// A negative int widened to size_t is a huge value, so each is refused here.
		ArgumentOutOfRangeException.ThrowIfNegative(width);
		ArgumentOutOfRangeException.ThrowIfNegative(height);
		// In long, so 65536 * 65536 cannot wrap to 0 and match empty costs.
		long cellCount = (long)width * height;
		if (stepCosts.Length != cellCount)
		{
			throw new ArgumentException(
				$"stepCosts has {stepCosts.Length} entries, width * height is {cellCount}",
				nameof(stepCosts));
		}
		var nativeSources = new nuint[sources.Length];
		for (int index = 0; index < sources.Length; ++index)
		{
			if (sources[index] < 0)
			{
				throw new ArgumentOutOfRangeException(
					nameof(sources), sources[index], "every source must be non-negative");
			}
			nativeSources[index] = (nuint)sources[index];
		}

		// cellCount equals a span length here, so it fits an array.
		var distances = new uint[stepCosts.Length];
		int status;
		fixed (byte* costsPointer = stepCosts)
		fixed (nuint* sourcesPointer = nativeSources)
		fixed (uint* distancesPointer = distances)
		{
			status = dijkstraMap(
				(nuint)width,
				(nuint)height,
				costsPointer,
				(int)connectivity,
				sourcesPointer,
				(nuint)nativeSources.Length,
				distancesPointer);
		}
		if (status != 0)
		{
			throw StatusException(status);
		}
		return Array.ConvertAll(distances, ToDistance);
	}

	/// <summary>Unloads the DLL; later calls throw ObjectDisposedException. A second call does nothing.</summary>
	/// <example>
	/// <code>
	/// library.Dispose();
	/// library.DijkstraMap(1, 1, [1], Connectivity.FourWay, [0]);  // throws ObjectDisposedException
	/// </code>
	/// </example>
	public void Dispose()
	{
		if (isDisposed)
		{
			return;
		}
		isDisposed = true;
		NativeLibrary.Free(libraryHandle);
	}

	/// <summary>
	/// The exception for a C status other than UNDEAD_OK, its message naming the status; the
	/// table is the one in docs/csharp-binding-contract.md.
	/// </summary>
	/// <example>
	/// <code>
	/// StatusException(5).GetType();  // -> typeof(OverflowException)
	/// StatusException(99).Message;   // -> "undead_dijkstra_map returned unknown status 99"
	/// </code>
	/// </example>
	/// <param name="status">The status undead_dijkstra_map returned.</param>
	/// <returns>The exception to throw; a binding or library defect is InvalidOperationException.</returns>
	internal static Exception StatusException(int status)
	{
		string name = status >= 0 && status < StatusNames.Length ? StatusNames[status] : $"unknown status {status}";
		string message = $"undead_dijkstra_map returned {name}";
		return status switch
		{
			2 => new ArgumentException(message),
			3 => new ArgumentOutOfRangeException(null, message),
			4 => new ArgumentException(message),
			5 => new OverflowException(message),
			6 => new InsufficientMemoryException(message),
			_ => new InvalidOperationException(message),
		};
	}

	/// <summary>A distance as C wrote it, with UNDEAD_UNREACHED as null.</summary>
	/// <example>
	/// <code>
	/// ToDistance(5);               // -> 5
	/// ToDistance(uint.MaxValue);   // -> null
	/// </code>
	/// </example>
	/// <param name="distance">One entry of C's output.</param>
	/// <returns>The distance, or null for an unreached cell.</returns>
	private static uint? ToDistance(uint distance)
	{
		return distance == Unreached ? null : distance;
	}
}

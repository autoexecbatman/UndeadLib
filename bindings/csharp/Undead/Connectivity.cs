// Connectivity: which neighbours a cell has, as UndeadLibrary.DijkstraMap takes it.

namespace Undead;

/// <summary>Which neighbours a cell has; the values are the C API's.</summary>
public enum Connectivity
{
	/// <summary>The four cells sharing an edge.</summary>
	FourWay = 4,

	/// <summary>Those four and the four diagonals.</summary>
	EightWay = 8,
}

/**
 * @file undead.mjs
 * JavaScript binding of UndeadLib's C API, over its WebAssembly build
 * (undead_wasm.mjs and undead_wasm.wasm, from an Emscripten build of the
 * repository). Works in Node and in a browser.
 *
 * Entry points: UndeadLibrary.load, new UndeadLibrary(wasm) for a module the
 * caller instantiated itself, UndeadLibrary#dijkstraMap, Connectivity and
 * UndeadError. Contract: docs/js-binding-contract.md.
 *
 * @example
 *   import { Connectivity, UndeadError, UndeadLibrary } from "./undead.mjs";
 *
 *   // The caller names the generated module; importing this file loads nothing.
 *   const library = await UndeadLibrary.load(new URL("./undead_wasm.mjs", import.meta.url));
 *
 *   // A corridor of seven cells; the door at cell 4 costs 2 to enter.
 *   const costs = Uint8Array.from([1, 1, 1, 1, 2, 1, 1]);
 *   library.dijkstraMap(7, 1, costs, Connectivity.EIGHT_WAY, [0]);
 *   // -> [0, 1, 2, 3, 5, 6, 7]      cost 0 is a wall; unreached cells are null
 *
 *   library.dijkstraMap(7, 1, costs, Connectivity.EIGHT_WAY, [7]);
 *   // throws UndeadError, .status === "UNDEAD_ERROR_SOURCE_OUT_OF_RANGE"
 *   library.dijkstraMap(7, 1, [1, 1], Connectivity.EIGHT_WAY, [0]);
 *   // throws TypeError: costs must be a Uint8Array
 */

/** Neighbourhoods: the four cells sharing an edge, or those and the four diagonals. */
export const Connectivity = Object.freeze({ FOUR_WAY: 4, EIGHT_WAY: 8 });

/** The C status names, indexed by status code, as undead.h numbers them. */
const STATUS_NAMES = Object.freeze([
	"UNDEAD_OK",
	"UNDEAD_ERROR_NULL_ARGUMENT",
	"UNDEAD_ERROR_GRID_SIZE",
	"UNDEAD_ERROR_SOURCE_OUT_OF_RANGE",
	"UNDEAD_ERROR_CONNECTIVITY",
	"UNDEAD_ERROR_DISTANCE_OVERFLOW",
	"UNDEAD_ERROR_OUT_OF_MEMORY",
	"UNDEAD_ERROR_INTERNAL",
]);

/** UNDEAD_UNREACHED, UINT32_MAX: the distance C writes for a cell no source reaches. */
const UNREACHED = 0xffffffff;

/** The largest value a wasm32 size_t holds. */
const SIZE_MAX = 0xffffffff;

/**
 * A C status other than UNDEAD_OK, carried as its name.
 *
 * @example
 *   try { library.dijkstraMap(2, 1, costs, 6, [0]); }
 *   catch (error) { error.status; }   // -> "UNDEAD_ERROR_CONNECTIVITY"
 */
export class UndeadError extends Error {
	/** @param {string} status - The status name, as undead.h spells it. */
	constructor(status) {
		super(`undead_c: ${status}`);
		this.name = "UndeadError";
		this.status = status;
	}
}

/**
 * Refuses a value that would wrap on its way into a 32-bit size_t.
 *
 * @example
 *   requireSize("width", 7);       // returns nothing
 *   requireSize("width", 2 ** 32);
 *   // throws RangeError: width must be an integer in [0, 4294967295], got 4294967296
 *
 * @param {string} name - What the value is, for the message.
 * @param {number} value - The value to check.
 * @throws {RangeError} Unless value is an integer in [0, 2^32 - 1].
 */
function requireSize(name, value) {
	if (!Number.isInteger(value) || value < 0 || value > SIZE_MAX) {
		throw new RangeError(`${name} must be an integer in [0, ${SIZE_MAX}], got ${value}`);
	}
}

/** The loaded WebAssembly module, and the calls made through it. */
export class UndeadLibrary {
	/** The instantiated Emscripten module: its exports and its heap views. */
	#wasm;

	/**
	 * Wraps a module the caller has already instantiated.
	 *
	 * @example
	 *   const { default: createModule } = await import("./undead_wasm.mjs");
	 *   const library = new UndeadLibrary(await createModule());
	 *
	 * @param {object} wasm - An instantiated undead_wasm module.
	 */
	constructor(wasm) {
		this.#wasm = wasm;
	}

	/**
	 * Imports and instantiates the generated module.
	 *
	 * @example
	 *   const library = await UndeadLibrary.load("./build-wasm/bin/undead_wasm.mjs");
	 *
	 * @param {string | URL} moduleUrl - Where undead_wasm.mjs is.
	 * @returns {Promise<UndeadLibrary>} The library, ready to call.
	 */
	static async load(moduleUrl) {
		const { default: createModule } = await import(moduleUrl);
		return new UndeadLibrary(await createModule());
	}

	/**
	 * Distance from the nearest source to every cell, by Dijkstra's algorithm in C.
	 * A cell's cost is paid to enter it, and cost 0 is a wall. Arguments are
	 * checked here for what wasm would misread; the rest is refused by C.
	 *
	 * @example
	 *   const room = new Uint8Array(9).fill(1);              // 3 x 3, all floor
	 *   library.dijkstraMap(3, 3, room, Connectivity.FOUR_WAY, [0])[8];  // -> 4
	 *   library.dijkstraMap(3, 3, room, Connectivity.EIGHT_WAY, [0])[8]; // -> 2
	 *
	 * @param {number} width - Cells per row.
	 * @param {number} height - Rows.
	 * @param {Uint8Array} stepCosts - width * height costs, indexed row * width + column.
	 * @param {number} connectivity - A Connectivity value.
	 * @param {number[]} sources - Cell indices at distance 0.
	 * @returns {(number | null)[]} One distance per cell, null where no source reaches.
	 * @throws {TypeError} If stepCosts is not a Uint8Array.
	 * @throws {RangeError} If a size, source or connectivity would wrap, or the costs are not width * height long.
	 * @throws {UndeadError} If C refuses: a source outside the grid, an unknown connectivity, a distance overflow.
	 */
	dijkstraMap(width, height, stepCosts, connectivity, sources) {
		// Everything that wraps or overruns on the way into wasm is refused first.
		requireSize("width", width);
		requireSize("height", height);
		if (!(stepCosts instanceof Uint8Array)) {
			throw new TypeError("costs must be a Uint8Array");
		}
		const cellCount = width * height;
		if (stepCosts.length !== cellCount) {
			throw new RangeError(`costs has ${stepCosts.length} entries, width * height is ${cellCount}`);
		}
		for (const source of sources) {
			requireSize("source", source);
		}
		// C takes an int; anything outside int32 would arrive as some other int.
		if (!Number.isInteger(connectivity) || connectivity < -(2 ** 31) || connectivity >= 2 ** 31) {
			throw new RangeError(`connectivity must be a 32-bit integer, got ${connectivity}`);
		}

		const wasm = this.#wasm;
		// Emscripten's malloc(0) returns a unique non-null pointer, so an empty grid needs no special case.
		const costsPointer = wasm._malloc(cellCount);
		const sourcesPointer = wasm._malloc(sources.length * 4);
		const distancesPointer = wasm._malloc(cellCount * 4);
		try {
			if (costsPointer === 0 || sourcesPointer === 0 || distancesPointer === 0) {
				throw new UndeadError("UNDEAD_ERROR_OUT_OF_MEMORY");
			}
			// Heap views are re-read after each allocation, since growth replaces them.
			wasm.HEAPU8.set(stepCosts, costsPointer);
			wasm.HEAPU32.set(sources, sourcesPointer / 4);
			const status = wasm._undead_dijkstra_map(
				width, height, costsPointer, connectivity, sourcesPointer, sources.length, distancesPointer);
			if (status !== 0) {
				throw new UndeadError(STATUS_NAMES[status] ?? `unknown status ${status}`);
			}
			const distances = wasm.HEAPU32.subarray(distancesPointer / 4, distancesPointer / 4 + cellCount);
			return Array.from(distances, (distance) => (distance === UNREACHED ? null : distance));
		} finally {
			// free(0) is a no-op, so every path frees all three.
			wasm._free(distancesPointer);
			wasm._free(sourcesPointer);
			wasm._free(costsPointer);
		}
	}
}

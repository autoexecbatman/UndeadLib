/**
 * @file dijkstra_map.test.mjs
 * UndeadLibrary.dijkstraMap against hand-worked answers and a Bellman-Ford
 * oracle; every refusal the binding makes before wasm, every reachable C
 * status, and the guarantee that wasm memory does not grow across calls.
 *
 * Run from bindings/js with UNDEAD_JS_MODULE naming the built module:
 *   $env:UNDEAD_JS_MODULE = "D:/repo/UndeadLib/build-wasm/bin/undead_wasm.mjs"
 *   node --test
 */
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { before, test } from "node:test";

import { Connectivity, UndeadError, UndeadLibrary } from "../undead.mjs";

let library;
let wasm;

// One instance for every test; the module is the build's, named by CTest.
before(async () => {
	const modulePath = process.env.UNDEAD_JS_MODULE;
	assert.ok(modulePath, "UNDEAD_JS_MODULE must name the built undead_wasm.mjs");
	const { default: createModule } = await import(pathToFileURL(modulePath));
	wasm = await createModule();
	library = new UndeadLibrary(wasm);
});

/**
 * A small seeded generator (mulberry32), so random grids repeat exactly.
 * @param {number} seed - Any 32-bit integer.
 * @returns {() => number} Uniform values in [0, 1).
 */
function seededRandom(seed) {
	let state = seed >>> 0;
	return function next() {
		state = (state + 0x6d2b79f5) >>> 0;
		let mixed = Math.imul(state ^ (state >>> 15), state | 1);
		mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
		return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
	};
}

/**
 * Shortest distances by relaxing every grid edge until nothing changes;
 * neighbours are enumerated here by offset, not by the library.
 * @returns {(number | null)[]} One distance per cell, null if unreached.
 */
function bellmanFord(width, height, costs, isEightWay, sources) {
	const distances = new Array(width * height).fill(null);
	for (const source of sources) {
		distances[source] = 0;
	}
	let isChanged = true;
	while (isChanged) {
		isChanged = false;
		for (let row = 0; row < height; ++row) {
			for (let column = 0; column < width; ++column) {
				const here = distances[row * width + column];
				if (here === null) {
					continue;
				}
				for (let rowOffset = -1; rowOffset <= 1; ++rowOffset) {
					for (let columnOffset = -1; columnOffset <= 1; ++columnOffset) {
						const isSelf = rowOffset === 0 && columnOffset === 0;
						const isDiagonal = rowOffset !== 0 && columnOffset !== 0;
						const nextRow = row + rowOffset;
						const nextColumn = column + columnOffset;
						if (isSelf || (isDiagonal && !isEightWay)) {
							continue;
						}
						if (nextRow < 0 || nextColumn < 0 || nextRow >= height || nextColumn >= width) {
							continue;
						}
						const target = nextRow * width + nextColumn;
						if (costs[target] === 0) {
							continue;
						}
						const candidate = here + costs[target];
						if (distances[target] === null || candidate < distances[target]) {
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

test("load imports and instantiates the module it is given", async () => {
	const loaded = await UndeadLibrary.load(pathToFileURL(process.env.UNDEAD_JS_MODULE).href);
	assert.deepEqual(
		loaded.dijkstraMap(3, 1, Uint8Array.from([1, 2, 1]), Connectivity.FOUR_WAY, [0]),
		[0, 2, 3]);
});

test("the door corridor costs two to enter the door", () => {
	const costs = Uint8Array.from([1, 1, 1, 1, 2, 1, 1]);
	assert.deepEqual(
		library.dijkstraMap(7, 1, costs, Connectivity.EIGHT_WAY, [0]),
		[0, 1, 2, 3, 5, 6, 7]);
});

test("a wall leaves the far side null", () => {
	const costs = Uint8Array.from([1, 0, 1]);
	assert.deepEqual(
		library.dijkstraMap(3, 1, costs, Connectivity.FOUR_WAY, [0]),
		[0, null, null]);
});

test("eight-way cuts the corner four-way walks", () => {
	const room = new Uint8Array(9).fill(1);
	assert.equal(library.dijkstraMap(3, 3, room, Connectivity.FOUR_WAY, [0])[8], 4);
	assert.equal(library.dijkstraMap(3, 3, room, Connectivity.EIGHT_WAY, [0])[8], 2);
});

test("no sources leaves every cell null", () => {
	const costs = Uint8Array.from([1, 1]);
	assert.deepEqual(
		library.dijkstraMap(2, 1, costs, Connectivity.FOUR_WAY, []),
		[null, null]);
});

test("an empty grid returns no distances", () => {
	assert.deepEqual(
		library.dijkstraMap(0, 4, new Uint8Array(0), Connectivity.FOUR_WAY, []),
		[]);
});

test("random grids agree with Bellman-Ford", () => {
	for (let seed = 1; seed <= 100; ++seed) {
		const random = seededRandom(seed);
		const width = 1 + Math.floor(random() * 12);
		const height = 1 + Math.floor(random() * 12);
		const costs = new Uint8Array(width * height);
		for (let cell = 0; cell < costs.length; ++cell) {
			costs[cell] = Math.floor(random() * 256);
		}
		const sources = [
			Math.floor(random() * costs.length),
			Math.floor(random() * costs.length),
		];
		for (const isEightWay of [false, true]) {
			const connectivity = isEightWay ? Connectivity.EIGHT_WAY : Connectivity.FOUR_WAY;
			assert.deepEqual(
				library.dijkstraMap(width, height, costs, connectivity, sources),
				bellmanFord(width, height, costs, isEightWay, sources),
				`seed ${seed}, eight-way ${isEightWay}`);
		}
	}
});

test("costs that are not a Uint8Array are refused", () => {
	assert.throws(
		() => library.dijkstraMap(2, 1, [1, 1], Connectivity.FOUR_WAY, [0]),
		TypeError);
	assert.throws(
		() => library.dijkstraMap(2, 1, Uint16Array.from([1, 1]), Connectivity.FOUR_WAY, [0]),
		TypeError);
});

test("costs of the wrong length are refused, short or long", () => {
	assert.throws(
		() => library.dijkstraMap(3, 3, new Uint8Array(7), Connectivity.FOUR_WAY, [0]),
		{ name: "RangeError", message: /width \* height/ });
	assert.throws(
		() => library.dijkstraMap(3, 3, new Uint8Array(10), Connectivity.FOUR_WAY, [0]),
		{ name: "RangeError", message: /width \* height/ });
});

test("a width that would wrap on its way into wasm is refused", () => {
	// With height 0 the empty array matches, so only the width check refuses.
	for (const width of [-1, 2 ** 32, 1.5]) {
		assert.throws(
			() => library.dijkstraMap(width, 0, new Uint8Array(0), Connectivity.FOUR_WAY, []),
			{ name: "RangeError", message: /^width / },
			`width ${width}`);
	}
});

test("a height that would wrap on its way into wasm is refused", () => {
	for (const height of [-1, 2 ** 32, 0.5]) {
		assert.throws(
			() => library.dijkstraMap(0, height, new Uint8Array(0), Connectivity.FOUR_WAY, []),
			{ name: "RangeError", message: /^height / },
			`height ${height}`);
	}
});

test("a source that would wrap on its way into wasm is refused", () => {
	// 2 ** 32 would wrap to 0, a real cell, and flood from the wrong place.
	const costs = Uint8Array.from([1, 1]);
	for (const source of [-1, 2 ** 32, 0.5]) {
		assert.throws(
			() => library.dijkstraMap(2, 1, costs, Connectivity.FOUR_WAY, [source]),
			{ name: "RangeError", message: /^source / },
			`source ${source}`);
	}
});

test("a connectivity that would wrap on its way into wasm is refused", () => {
	// 2 ** 32 + 4 would arrive as 4, a valid four-way.
	const costs = Uint8Array.from([1, 1]);
	assert.throws(
		() => library.dijkstraMap(2, 1, costs, 2 ** 32 + 4, [0]),
		{ name: "RangeError", message: /^connectivity / });
});

test("a source outside the grid is refused by C", () => {
	assert.throws(
		() => library.dijkstraMap(7, 1, new Uint8Array(7).fill(1), Connectivity.FOUR_WAY, [7]),
		(error) => error instanceof UndeadError && error.status === "UNDEAD_ERROR_SOURCE_OUT_OF_RANGE");
});

test("an unknown connectivity is refused by C", () => {
	assert.throws(
		() => library.dijkstraMap(2, 1, Uint8Array.from([1, 1]), 6, [0]),
		(error) => error instanceof UndeadError && error.status === "UNDEAD_ERROR_CONNECTIVITY");
});

test("a distance reaching UINT32_MAX is refused by C", () => {
	// Cost-255 corridor: cell 16843009 is the first at 4294967295.
	const width = 16843010;
	assert.throws(
		() => library.dijkstraMap(width, 1, new Uint8Array(width).fill(255), Connectivity.FOUR_WAY, [0]),
		(error) => error instanceof UndeadError && error.status === "UNDEAD_ERROR_DISTANCE_OVERFLOW");
});

test("wasm memory does not grow across many calls, refusals included", async () => {
	// A fresh instance: a heap other tests grew would absorb a leak without growing.
	const { default: createModule } = await import(pathToFileURL(process.env.UNDEAD_JS_MODULE));
	const freshWasm = await createModule();
	const freshLibrary = new UndeadLibrary(freshWasm);
	const heapBytes = freshWasm.HEAPU8.length;
	// 40000 cells, every one a source: each buffer is 40 KB or more, and
	// 1000 calls leaking any one of them would add 40 MB to a 17 MB heap.
	const costs = new Uint8Array(40000).fill(1);
	const everyCell = Array.from(costs.keys());
	const oneOutside = [...everyCell, 40000];
	for (let call = 0; call < 500; ++call) {
		freshLibrary.dijkstraMap(200, 200, costs, Connectivity.EIGHT_WAY, everyCell);
		assert.throws(
			() => freshLibrary.dijkstraMap(200, 200, costs, Connectivity.EIGHT_WAY, oneOutside),
			UndeadError);
	}
	assert.equal(freshWasm.HEAPU8.length, heapBytes);
});

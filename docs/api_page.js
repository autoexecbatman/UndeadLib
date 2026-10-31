/**
 * The script api_page.py inlines into build/docs/api.html: filters the
 * sidebar links and the entries by name as the reader types. "/" focuses the
 * filter and Escape clears it. Every element carrying data-name, a lower-case
 * copy of its declaration's name, is shown or hidden by the filter; while a
 * query is active, file overviews and files with no match are hidden too,
 * so what matches is what the page shows.
 */
(function () {
	const filter = document.getElementById("filter");
	const named = Array.from(document.querySelectorAll("[data-name]"));
	const files = Array.from(document.querySelectorAll("main article.file"));
	const sections = Array.from(document.querySelectorAll("main section"));
	const sidebarFiles = Array.from(document.querySelectorAll("#sidebar ul"));

	// True when the container holds at least one entry the filter shows.
	function hasVisible(container, selector) {
		return Array.from(container.querySelectorAll(selector)).some(
			function (element) {
				return !element.hidden;
			}
		);
	}

	// Shows what contains the query, by plain substring, so no character
	// the reader types needs escaping.
	function apply() {
		const query = filter.value.trim().toLowerCase();
		const isFiltering = query !== "";
		for (const element of named) {
			element.hidden =
				isFiltering && !element.dataset.name.includes(query);
		}
		// A file shows while filtering only if one of its entries matches,
		// and then without its overview.
		for (const file of files) {
			file.hidden = isFiltering && !hasVisible(file, ".entry");
			file.querySelector(".overview").hidden = isFiltering;
		}
		for (const section of sections) {
			section.hidden = isFiltering && !hasVisible(section, "article.file");
		}
		// The sidebar's file heading sits just before its list.
		for (const list of sidebarFiles) {
			const isEmpty = isFiltering && !hasVisible(list, "li");
			list.hidden = isEmpty;
			list.previousElementSibling.hidden = isEmpty;
		}
	}

	filter.addEventListener("input", apply);
	document.addEventListener("keydown", function (event) {
		if (event.key === "/" && document.activeElement !== filter) {
			event.preventDefault();
			filter.focus();
		} else if (event.key === "Escape" && document.activeElement === filter) {
			filter.value = "";
			apply();
			filter.blur();
		}
	});
})();

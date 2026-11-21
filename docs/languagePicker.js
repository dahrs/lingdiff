// Flat, alphabetically-sorted language picker. Previously nested entries under their family/
// macrolanguage (e.g. Levantine Arabic under the Arabic group) with depth-based indentation
// and styling — at ~2444 entries that nesting wasn't legible as "grouped by family" any more,
// it just looked like an inconsistent mix of bold/grey rows in a non-alphabetical order (and
// the same inconsistency carried into the type-to-search results, which filtered that same
// pre-nested order rather than showing alphabetical matches). Flat A-Z, same style for every
// row, is what actually reads as a usable list at this scale; each row's full classification
// path is still available on hover (see its `title`) for anyone who wants the family context.
// A plain <select>'s <option> elements can't take arbitrary padding/overflow styling
// reliably across browsers, so this is still a small custom listbox built from styled <div>s.

/** Does this entry match a type-to-search query? Word-prefix, not a plain substring and not
 * requiring the match be the very first word — typing "Beirut" should find "Arabic
 * (Beirut)", not just names that literally start with "Beirut". Matches against the
 * language's own display name and its ISO 639-3 code (e.g. typing "spa" finds Spanish). */
function entryMatchesQuery(entry, query) {
  if (!query) return true;
  const words = entry.name
    .toLowerCase()
    .replace(/[-()]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  if (words.some((word) => word.startsWith(query))) return true;
  return !!entry.iso639_3 && entry.iso639_3.toLowerCase().startsWith(query);
}

/** Wires up one .lang-picker container (a .picker-button + a .picker-panel, per index.html)
 * against the given entries. Calls onSelect(entry) when the user picks one. With ~2400
 * languages in the full list, scrolling to find one is tedious — the panel's first child is
 * a type-to-search box that filters the (alphabetical) rows below it as you type, rather than
 * requiring you to scroll through the whole list. */
function createLanguagePicker(container, entries, onSelect) {
  const button = container.querySelector(".picker-button");
  const panel = container.querySelector(".picker-panel");
  const sortedEntries = [...entries].sort((a, b) => a.name.localeCompare(b.name));

  panel.innerHTML = "";
  let selected = null;

  const selectEntry = (entry, { notify } = { notify: true }) => {
    selected = entry;
    button.textContent = entry.name;
    closePanel();
    if (notify) onSelect(entry);
  };

  const searchInput = document.createElement("input");
  searchInput.type = "text";
  searchInput.className = "picker-search";
  searchInput.placeholder = "Type to search…";
  searchInput.setAttribute("autocomplete", "off");
  panel.appendChild(searchInput);

  const noMatches = document.createElement("p");
  noMatches.className = "picker-no-matches";
  noMatches.textContent = "No languages match.";
  noMatches.hidden = true;
  panel.appendChild(noMatches);

  const rowEls = [];
  for (const entry of sortedEntries) {
    const row = document.createElement("div");
    row.className = "picker-option";
    row.textContent = entry.name + (entry.iso639_3 ? ` (${entry.iso639_3})` : "");
    row.title = entry.classification_path.join(" → ");
    row.addEventListener("click", () => selectEntry(entry));
    panel.appendChild(row);
    rowEls.push({ entry, row });
  }

  const applyFilter = () => {
    const query = searchInput.value.trim().toLowerCase();
    let anyVisible = false;
    for (const { entry, row } of rowEls) {
      const matches = entryMatchesQuery(entry, query);
      row.hidden = !matches;
      anyVisible = anyVisible || matches;
    }
    noMatches.hidden = anyVisible;
  };

  searchInput.addEventListener("input", applyFilter);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePanel();
    } else if (event.key === "Enter") {
      const firstVisible = rowEls.find(({ row }) => !row.hidden);
      if (firstVisible) selectEntry(firstVisible.entry);
    }
  });
  searchInput.addEventListener("click", (event) => event.stopPropagation());

  const closePanel = () => {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
  };
  const openPanel = () => {
    document.querySelectorAll(".picker-panel").forEach((p) => {
      if (p !== panel) p.hidden = true;
    });
    searchInput.value = "";
    applyFilter();
    panel.hidden = false;
    button.setAttribute("aria-expanded", "true");
    searchInput.focus();
  };

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (panel.hidden) openPanel();
    else closePanel();
  });
  document.addEventListener("click", (event) => {
    if (!container.contains(event.target)) closePanel();
  });

  return {
    getSelected: () => selected,
    /** Programmatically selects an entry by glottocode (e.g. from the nearest/farthest
     * panel's "load this comparison" cards) without re-firing onSelect — the caller already
     * knows what it's doing and drives the comparison itself. */
    selectByGlottocode: (glottocode) => {
      const entry = entries.find((e) => e.glottocode === glottocode);
      if (entry) selectEntry(entry, { notify: false });
    },
  };
}

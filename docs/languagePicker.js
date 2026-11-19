// Hierarchical language picker: nests each index entry under whichever other entry's
// identity name shows up deepest in its own classification path (e.g. Levantine/Egyptian
// Arabic under the Arabic macrolanguage group, Romanian under the Romance group), so the
// dropdown shows macrolanguage/dialect relationships directly rather than a flat
// alphabetical list. A plain <select>'s <option> elements can't reliably take different
// font-weight/indentation across browsers, so this is a small custom listbox built from
// styled <div>s instead.

/** Is `candidateName` one whole word within `element`? Word-boundary match, not a plain
 * substring — a plain substring check matches "German" inside "Germanic languages" (wrong:
 * German is a sibling of other Germanic languages, not their parent), while still matching
 * "Arabic" inside "Arabic (Egyptian)" (right: the parenthetical is a separate word). */
function pathElementMatchesName(element, candidateName) {
  const words = element
    .toLowerCase()
    .replace(/[-()]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  return words.includes(candidateName.toLowerCase());
}

/** Does `candidateName` identify one of the steps in `path`? Needed because the same family
 * can appear at a different depth, or not as its own path element at all, depending on which
 * source (Wikidata's deep chain vs. WALS's shallower fallback) a given entry's classification
 * came from. Confirmed live: Egyptian Arabic's WALS-fallback path jumps straight from
 * "Semitic" to the leaf name "Arabic (Egyptian)", with no separate "Arabic" element at all —
 * exact-position prefix matching against the Arabic group's Wikidata-based path (which does
 * have a standalone "Arabic" element) would leave it unnested entirely. Returns the deepest
 * matching index, or -1. */
function deepestMatchIndex(path, candidateName) {
  let deepest = -1;
  path.forEach((name, index) => {
    if (pathElementMatchesName(name, candidateName)) deepest = index;
  });
  return deepest;
}

/** Builds a forest: for each entry, the nearest *other* entry whose own identity name (the
 * last step of its classification path) shows up deepest in this entry's path becomes its
 * parent; entries with no such match become roots. */
function buildLanguageTree(entries) {
  const nodes = entries.map((entry) => ({ entry, children: [] }));
  const roots = [];

  for (const node of nodes) {
    // Excludes the entry's own leaf position from the search entirely (not just filtered
    // after) — otherwise an entry whose own leaf name happens to contain the candidate's
    // name as a word (confirmed live: "Arabic (Beirut)" contains the word "Arabic", the
    // Arabic group's own identity name) would match itself more "deeply" than the real
    // ancestor match further up the path, discarding the correct match instead of just
    // ignoring the coincidental one.
    const fullPath = node.entry.classification_path;
    const ancestorPath = fullPath.slice(0, -1);
    const leafName = fullPath.at(-1);
    let bestParent = null;
    let bestIndex = -1;
    for (const candidate of nodes) {
      if (candidate === node) continue;
      const candidateName = candidate.entry.classification_path.at(-1);
      const matchIndex = deepestMatchIndex(ancestorPath, candidateName);
      if (matchIndex === -1) continue;
      if (matchIndex > bestIndex) {
        bestIndex = matchIndex;
        bestParent = candidate;
      }
    }
    // Fallback, only when nothing matched in the ancestor chain at all: check the entry's
    // own leaf name too. Needed for sources sparse enough to skip a level entirely —
    // confirmed live: Egyptian Arabic's WALS-fallback path has no "Arabic" ancestor element
    // at all (it jumps straight from "Semitic" to the leaf "Arabic (Egyptian)"), so "Arabic"
    // only ever shows up as a word inside its own leaf name. This is deliberately a
    // last-resort tier, not merged into the main search above — Levantine Arabic's leaf name
    // ALSO contains the word "Arabic" alongside a real ancestor match at a deeper index, and
    // blindly preferring whichever match is "deepest" across both would have picked the
    // coincidental self-match over the correct ancestor one (that was the actual bug here).
    if (!bestParent) {
      for (const candidate of nodes) {
        if (candidate === node) continue;
        const candidateName = candidate.entry.classification_path.at(-1);
        if (pathElementMatchesName(leafName, candidateName)) {
          bestParent = candidate;
          break;
        }
      }
    }
    if (bestParent) bestParent.children.push(node);
    else roots.push(node);
  }

  const sortRec = (list) => {
    list.sort((a, b) => a.entry.name.localeCompare(b.entry.name));
    list.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}

function flattenTree(nodes, depth = 0, out = []) {
  for (const node of nodes) {
    out.push({ entry: node.entry, depth });
    flattenTree(node.children, depth + 1, out);
  }
  return out;
}

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
 * a type-to-search box that filters the rows below it as you type, rather than requiring you
 * to scroll through the whole (tree-nested) list. */
function createLanguagePicker(container, entries, onSelect) {
  const button = container.querySelector(".picker-button");
  const panel = container.querySelector(".picker-panel");
  const rows = flattenTree(buildLanguageTree(entries));

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
  for (const { entry, depth } of rows) {
    const row = document.createElement("div");
    row.className = `picker-option depth-${Math.min(depth, 2)}`;
    row.style.paddingLeft = `${0.8 + depth * 1.4}rem`;
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

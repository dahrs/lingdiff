// Reusable "shared / only-in-A / only-in-B" renderer — the building block behind the
// public-friendly requirement (see the plan): phonemes, grammatical cases/tenses/moods/
// aspects, and WALS tense-aspect categories all reduce to this same three-column view.

function renderSetDiff(container, { shared, onlyA, onlyB }, labelA, labelB) {
  container.innerHTML = "";
  const grid = document.createElement("div");
  grid.className = "diff-grid";

  const column = (title, items, cls) => {
    const col = document.createElement("div");
    col.className = `diff-col ${cls}`;
    const heading = document.createElement("h4");
    heading.textContent = `${title} (${items.length})`;
    col.appendChild(heading);
    if (items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "diff-empty";
      empty.textContent = "none";
      col.appendChild(empty);
    } else {
      const list = document.createElement("ul");
      for (const item of items) {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
      }
      col.appendChild(list);
    }
    return col;
  };

  grid.appendChild(column(`Only in ${labelA}`, onlyA, "diff-only-a"));
  grid.appendChild(column("Shared", shared, "diff-shared"));
  grid.appendChild(column(`Only in ${labelB}`, onlyB, "diff-only-b"));
  container.appendChild(grid);
}

/** Row-aligned side-by-side view for feature comparisons (e.g. word order) — each row has
 * its own two values and a match/mismatch mark, rather than a set overlap. */
function renderRowDiff(container, rows, labelA, labelB) {
  container.innerHTML = "";
  const table = document.createElement("table");
  table.className = "row-diff-table";
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr><th>Feature</th><th>${labelA}</th><th>${labelB}</th><th></th></tr>`;
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    const mark = row.match === null ? "" : row.match ? "✓" : "✗";
    tr.className = row.match === false ? "row-mismatch" : row.match === true ? "row-match" : "";
    tr.innerHTML = `<td>${row.name}</td><td>${row.valueA ?? "—"}</td><td>${row.valueB ?? "—"}</td><td class="row-mark">${mark}</td>`;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

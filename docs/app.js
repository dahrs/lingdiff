// Picker UI + orchestration: fetches data/index.json once, lazily fetches the two selected
// profiles, and renders the comparison. No LLM/network calls beyond those three fetches.

let indexEntries = [];
const profileCache = new Map();
let pickerA = null;
let pickerB = null;

async function loadIndex() {
  const response = await fetch("data/index.json");
  indexEntries = await response.json();
  pickerA = createLanguagePicker(document.getElementById("picker-a"), indexEntries, renderNearestPanel);
  pickerB = createLanguagePicker(document.getElementById("picker-b"), indexEntries, () => {});
  document.querySelectorAll(".picker-button").forEach((b) => (b.textContent = "Select a language…"));
}

/** Shows language A's precomputed closest/farthest match (from index.json — no extra fetch,
 * see schema.NearestNeighbor) as soon as it's picked, independent of whatever's picked for
 * B. Only leaf languages carry this (see nearest_neighbors.py); a "group" entry (a family or
 * macrolanguage) shows a short note instead of a stale/wrong panel. */
function renderNearestPanel(entry) {
  const panel = document.getElementById("nearest-panel");
  if (entry.comparison_kind !== "leaf" || (!entry.closest && !entry.farthest)) {
    panel.innerHTML = entry.comparison_kind === "leaf"
      ? ""
      : `<p class="nearest-note">${entry.name} is a family/macrolanguage group — closest/farthest comparisons are only computed between individual languages.</p>`;
    return;
  }
  const side = (label, neighbor, cssClass) => {
    if (!neighbor) return "";
    const badge = scoreBadge(neighbor.score / 100);
    return `
      <button type="button" class="nearest-card ${cssClass}" data-glottocode="${neighbor.glottocode}">
        <span class="nearest-label">${label}</span>
        <span class="nearest-name">${neighbor.name}</span>
        <span class="nearest-score">${badge.percent} · ${badge.label}</span>
      </button>
    `;
  };
  panel.innerHTML = `
    <p class="nearest-heading">Among all languages in this list, relative to <strong>${entry.name}</strong>:</p>
    <div class="nearest-cards">
      ${side("Closest", entry.closest, "nearest-closest")}
      ${side("Most distant", entry.farthest, "nearest-farthest")}
    </div>
  `;
  panel.querySelectorAll(".nearest-card").forEach((card) => {
    card.addEventListener("click", () => {
      const neighborEntry = indexEntries.find((e) => e.glottocode === card.dataset.glottocode);
      if (!neighborEntry) return;
      pickerB.selectByGlottocode(neighborEntry.glottocode);
      onCompareClick();
    });
  });
}

async function loadProfile(glottocode) {
  if (profileCache.has(glottocode)) return profileCache.get(glottocode);
  const response = await fetch(`data/languages/${glottocode}.json`);
  const profile = await response.json();
  profileCache.set(glottocode, profile);
  return profile;
}

async function onCompareClick() {
  const entryA = pickerA?.getSelected();
  const entryB = pickerB?.getSelected();
  const resultsEl = document.getElementById("results");
  if (!entryA || !entryB) {
    resultsEl.innerHTML = '<p class="error">Pick two languages first.</p>';
    return;
  }
  resultsEl.innerHTML = '<p class="loading">Loading…</p>';
  const [a, b] = await Promise.all([loadProfile(entryA.glottocode), loadProfile(entryB.glottocode)]);
  const comparison = compareLanguages(a, b);
  renderComparison(resultsEl, comparison);
}

/** 0-1 distance -> {percent, label} for display — same scale/labels the overall score uses
 * (qualitativeLabel in compare.js), so a reader can compare a category's own score against
 * the overall number the same way. */
function scoreBadge(score) {
  if (score === null || score === undefined) return { percent: null, label: "no data" };
  const percent = Math.round(score * 100);
  return { percent, label: qualitativeLabel(percent) };
}

function renderComparison(container, comparison) {
  const { a, b, categories, overall, label } = comparison;
  container.innerHTML = "";

  const header = document.createElement("div");
  header.className = "result-header";
  header.innerHTML = `
    <h2>${a.name} vs. ${b.name}</h2>
    <div class="overall-score">
      <span class="score-number">${overall.score === null ? "—" : overall.score}</span>
      <span class="score-label">${label}</span>
      <span class="score-coverage">${overall.availableCount} of ${overall.totalCount} metrics available</span>
    </div>
    <p class="score-explainer">
      Overall distance score, 0–100: <strong>0 means identical</strong>, <strong>100 means maximally different</strong>
      across whichever categories had data for this pair. Each section below shows its own score the same way —
      click a section's title to see the detail behind it.
    </p>
  `;
  container.appendChild(header);

  const summaryEl = document.createElement("p");
  summaryEl.className = "summary-text";
  summaryEl.textContent = buildSummary(comparison);
  container.appendChild(summaryEl);

  container.appendChild(renderFamilySection(categories.family, a, b));
  container.appendChild(
    renderCollapsibleSection("Phonology — IPA phoneme inventory", categories.phonology.score, (body) => {
      if (!categories.phonology.available) return renderNoData(body);
      renderSetDiff(body, categories.phonology, a.name, b.name);
    }),
  );
  container.appendChild(
    renderCollapsibleSection("Syntax — word order", categories.wordOrder.score, (body) => {
      if (!categories.wordOrder.available) return renderNoData(body);
      renderRowDiff(body, categories.wordOrder.rows, a.name, b.name);
    }),
  );
  container.appendChild(renderMorphologySection(categories.morphology, a, b));
  container.appendChild(renderWritingSystemSection(categories.writingSystem, a, b));

  if (a.notable_features || b.notable_features) {
    const notable = document.createElement("div");
    notable.className = "category-section";
    notable.innerHTML = "<h3>Notable features</h3>";
    if (a.notable_features) notable.innerHTML += `<p><strong>${a.name}:</strong> ${a.notable_features.text}</p>`;
    if (b.notable_features) notable.innerHTML += `<p><strong>${b.name}:</strong> ${b.notable_features.text}</p>`;
    container.appendChild(notable);
  }
}

function renderNoData(container) {
  const note = document.createElement("p");
  note.className = "no-data";
  note.textContent = "No data available for this pair.";
  container.appendChild(note);
}

/** A native <details>/<summary> element — clicking the title toggles the body, with no
 * custom JS needed for that behavior. The summary shows a score badge (0-100 + label, same
 * scale as the overall score) next to the title, or "no data" when this category has none. */
function renderCollapsibleSection(title, score, bodyBuilder) {
  const details = document.createElement("details");
  details.className = "category-section";
  const badge = scoreBadge(score);
  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="section-title">${title}</span>
    <span class="section-badge ${badge.percent === null ? "badge-empty" : ""}">${badge.percent === null ? "no data" : `${badge.percent} · ${badge.label}`}</span>
  `;
  details.appendChild(summary);
  const body = document.createElement("div");
  body.className = "section-body";
  details.appendChild(body);
  bodyBuilder(body);
  return details;
}

function renderFamilySection(family, a, b) {
  return renderCollapsibleSection("Family classification", family.score, (body) => {
    const branches = document.createElement("div");
    branches.className = "family-branches";
    branches.innerHTML = `
      <div class="family-branch"><strong>${a.name}:</strong> ${family.pathA.join(" → ")}</div>
      <div class="family-branch"><strong>${b.name}:</strong> ${family.pathB.join(" → ")}</div>
      <div class="family-common">${family.commonAncestor ? `Common ancestor: ${family.commonAncestor}` : "No common ancestor found in this data."}</div>
    `;
    body.appendChild(branches);
  });
}

function renderMorphologySection(morphology, a, b) {
  return renderCollapsibleSection("Morphology — grammatical categories", morphology.score, (body) => {
    if (!morphology.available) return renderNoData(body);
    const subcats = [
      ["Grammatical cases", morphology.cases],
      ["Tenses", morphology.tenses],
      ["Moods", morphology.moods],
      ["Aspects", morphology.aspects],
      ["WALS tense/aspect typology", morphology.walsCategories],
    ];
    let anyRendered = false;
    for (const [label, diff] of subcats) {
      // A null score means one side had no data for this specific sub-category — rendering
      // the diff anyway would make "no data gathered" look like "confirmed zero" (see
      // compare.js's diffSets docs). Skip it rather than show something misleading.
      if (diff.score === null) continue;
      anyRendered = true;
      const sub = document.createElement("div");
      sub.className = "morphology-subcategory";
      const h4 = document.createElement("h4");
      const badge = scoreBadge(diff.score);
      h4.innerHTML = `${label} <span class="subcategory-badge">${badge.percent} · ${badge.label}</span>`;
      sub.appendChild(h4);
      const subBody = document.createElement("div");
      sub.appendChild(subBody);
      renderSetDiff(subBody, diff, a.name, b.name);
      body.appendChild(sub);
    }
    if (!anyRendered) renderNoData(body);
  });
}

function renderWritingSystemSection(ws, a, b) {
  return renderCollapsibleSection("Writing system", ws.score, (body) => {
    if (!ws.available) return renderNoData(body);
    if (ws.sharedTypes?.length && ws.shared.length === 0) {
      const note = document.createElement("p");
      note.className = "ws-type-note";
      note.textContent = `No exact script in common, but both use a ${ws.sharedTypes.join("/")} system.`;
      body.appendChild(note);
    }
    renderSetDiff(body, ws, a.name, b.name);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadIndex();
  document.getElementById("compare-btn").addEventListener("click", onCompareClick);
});

// Picker UI + orchestration: fetches data/index.json once, lazily fetches the two selected
// profiles, and renders the comparison. No LLM/network calls beyond those three fetches.

let indexEntries = [];
const profileCache = new Map();

async function loadIndex() {
  const response = await fetch("data/index.json");
  indexEntries = await response.json();
  populateSelect(document.getElementById("lang-a"));
  populateSelect(document.getElementById("lang-b"));
}

function populateSelect(select) {
  select.innerHTML = '<option value="">Select a language…</option>';
  const leaves = indexEntries.filter((e) => e.comparison_kind === "leaf");
  const groups = indexEntries.filter((e) => e.comparison_kind === "group");

  const addGroup = (label, entries) => {
    const optgroup = document.createElement("optgroup");
    optgroup.label = label;
    for (const entry of entries.sort((x, y) => x.name.localeCompare(y.name))) {
      const option = document.createElement("option");
      option.value = entry.glottocode;
      option.textContent = `${entry.name}${entry.iso639_3 ? ` (${entry.iso639_3})` : ""}`;
      optgroup.appendChild(option);
    }
    select.appendChild(optgroup);
  };

  addGroup("Languages & dialects", leaves);
  addGroup("Families & macrolanguage groups", groups);
}

async function loadProfile(glottocode) {
  if (profileCache.has(glottocode)) return profileCache.get(glottocode);
  const response = await fetch(`data/languages/${glottocode}.json`);
  const profile = await response.json();
  profileCache.set(glottocode, profile);
  return profile;
}

async function onCompareClick() {
  const glottocodeA = document.getElementById("lang-a").value;
  const glottocodeB = document.getElementById("lang-b").value;
  const resultsEl = document.getElementById("results");
  if (!glottocodeA || !glottocodeB) {
    resultsEl.innerHTML = '<p class="error">Pick two languages first.</p>';
    return;
  }
  resultsEl.innerHTML = '<p class="loading">Loading…</p>';
  const [a, b] = await Promise.all([loadProfile(glottocodeA), loadProfile(glottocodeB)]);
  const comparison = compareLanguages(a, b);
  renderComparison(resultsEl, comparison);
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
  `;
  container.appendChild(header);

  const summaryEl = document.createElement("p");
  summaryEl.className = "summary-text";
  summaryEl.textContent = buildSummary(comparison);
  container.appendChild(summaryEl);

  container.appendChild(renderFamilySection(categories.family, a, b));
  container.appendChild(renderCategorySection("Phonology — IPA phoneme inventory", categories.phonology, a, b, "set"));
  container.appendChild(renderCategorySection("Syntax — word order", categories.wordOrder, a, b, "row"));
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

function renderFamilySection(family, a, b) {
  const section = document.createElement("div");
  section.className = "category-section";
  section.innerHTML = "<h3>Family classification</h3>";
  const branches = document.createElement("div");
  branches.className = "family-branches";
  branches.innerHTML = `
    <div class="family-branch"><strong>${a.name}:</strong> ${family.pathA.join(" → ")}</div>
    <div class="family-branch"><strong>${b.name}:</strong> ${family.pathB.join(" → ")}</div>
    <div class="family-common">${family.commonAncestor ? `Common ancestor: ${family.commonAncestor}` : "No common ancestor found in this data."}</div>
  `;
  section.appendChild(branches);
  return section;
}

function renderCategorySection(title, category, a, b, kind) {
  const section = document.createElement("div");
  section.className = "category-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.appendChild(heading);
  if (!category.available) {
    const note = document.createElement("p");
    note.className = "no-data";
    note.textContent = "No data available for this pair.";
    section.appendChild(note);
    return section;
  }
  const body = document.createElement("div");
  section.appendChild(body);
  if (kind === "set") {
    renderSetDiff(body, category, a.name, b.name);
  } else {
    renderRowDiff(body, category.rows, a.name, b.name);
  }
  return section;
}

function renderMorphologySection(morphology, a, b) {
  const section = document.createElement("div");
  section.className = "category-section";
  section.innerHTML = "<h3>Morphology — grammatical categories</h3>";
  if (!morphology.available) {
    section.innerHTML += '<p class="no-data">No data available for this pair.</p>';
    return section;
  }
  const subcats = [
    ["Grammatical cases", morphology.cases],
    ["Tenses", morphology.tenses],
    ["Moods", morphology.moods],
    ["Aspects", morphology.aspects],
    ["WALS tense/aspect typology", morphology.walsCategories],
  ];
  for (const [label, diff] of subcats) {
    if (diff.shared.length + diff.onlyA.length + diff.onlyB.length === 0) continue;
    const sub = document.createElement("div");
    sub.className = "morphology-subcategory";
    const h4 = document.createElement("h4");
    h4.textContent = label;
    sub.appendChild(h4);
    const body = document.createElement("div");
    sub.appendChild(body);
    renderSetDiff(body, diff, a.name, b.name);
    section.appendChild(sub);
  }
  return section;
}

function renderWritingSystemSection(ws, a, b) {
  const section = document.createElement("div");
  section.className = "category-section";
  section.innerHTML = "<h3>Writing system</h3>";
  if (!ws.available) {
    section.innerHTML += '<p class="no-data">No data available for this pair.</p>';
    return section;
  }
  const row = document.createElement("div");
  row.className = "writing-system-row";
  const side = (name, data) =>
    data
      ? `<div class="ws-side"><strong>${name}:</strong> ${data.script_name} <span class="ws-type">(${data.script_type})</span></div>`
      : `<div class="ws-side"><strong>${name}:</strong> no data</div>`;
  row.innerHTML = side(a.name, ws.wsA) + side(b.name, ws.wsB);
  section.appendChild(row);
  return section;
}

document.addEventListener("DOMContentLoaded", () => {
  loadIndex();
  document.getElementById("compare-btn").addEventListener("click", onCompareClick);
});

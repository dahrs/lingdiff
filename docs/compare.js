// Pure comparison functions: given two LanguageProfile objects (as fetched from
// data/languages/<glottocode>.json), compute a per-category comparison. No network calls, no
// LLM calls — everything here is plain arithmetic/set-logic over already-fetched JSON, per
// the project's core design constraint (see README.md).

/** Family/genealogical distance via longest-common-prefix of the two classification paths
 * (both ordered root-first). Works the same whether either side is a "leaf" language or a
 * "group" (family/macrolanguage) entity — a group's path simply ends at itself. */
function compareFamily(a, b) {
  const pathA = a.classification.path.map((n) => n.name);
  const pathB = b.classification.path.map((n) => n.name);
  let commonDepth = 0;
  while (commonDepth < pathA.length && commonDepth < pathB.length && pathA[commonDepth] === pathB[commonDepth]) {
    commonDepth++;
  }
  const hopsA = pathA.length - commonDepth;
  const hopsB = pathB.length - commonDepth;
  const maxDepth = Math.max(pathA.length, pathB.length, 1);
  const score = Math.min(1, (hopsA + hopsB) / (2 * maxDepth));
  return {
    available: true,
    score,
    pathA,
    pathB,
    commonAncestor: commonDepth > 0 ? pathA[commonDepth - 1] : null,
    divergeAtA: pathA[commonDepth] ?? null,
    divergeAtB: pathB[commonDepth] ?? null,
  };
}

/** Three-column shared/only-A/only-B split of two string lists (order-insensitive, de-duped). */
function diffSets(listA, listB) {
  const setA = new Set(listA || []);
  const setB = new Set(listB || []);
  const shared = [...setA].filter((x) => setB.has(x)).sort();
  const onlyA = [...setA].filter((x) => !setB.has(x)).sort();
  const onlyB = [...setB].filter((x) => !setA.has(x)).sort();
  const union = shared.length + onlyA.length + onlyB.length;
  const score = union === 0 ? null : 1 - shared.length / union; // Jaccard distance
  return { shared, onlyA, onlyB, score };
}

function comparePhonology(a, b) {
  const phonemesA = a.phonology?.phonemes || [];
  const phonemesB = b.phonology?.phonemes || [];
  if (phonemesA.length === 0 && phonemesB.length === 0) return { available: false };
  const diff = diffSets(phonemesA, phonemesB);
  return { available: true, ...diff };
}

function compareWordOrder(a, b) {
  const featuresA = a.syntax?.features || [];
  const featuresB = b.syntax?.features || [];
  if (featuresA.length === 0 && featuresB.length === 0) return { available: false };
  const byCode = (list) => new Map(list.map((f) => [f.wals_code, f]));
  const mapA = byCode(featuresA);
  const mapB = byCode(featuresB);
  const codes = [...new Set([...mapA.keys(), ...mapB.keys()])].sort();
  const rows = codes.map((code) => {
    const fa = mapA.get(code);
    const fb = mapB.get(code);
    return {
      name: (fa || fb).name,
      valueA: fa ? fa.value : null,
      valueB: fb ? fb.value : null,
      match: fa && fb ? fa.value === fb.value : null,
    };
  });
  const comparable = rows.filter((r) => r.match !== null);
  const score = comparable.length === 0 ? null : 1 - comparable.filter((r) => r.match).length / comparable.length;
  return { available: true, rows, score };
}

function compareMorphology(a, b) {
  const morphA = a.morphology || {};
  const morphB = b.morphology || {};
  const cases = diffSets(morphA.grammatical_cases, morphB.grammatical_cases);
  const tenses = diffSets(morphA.tenses, morphB.tenses);
  const moods = diffSets(morphA.moods, morphB.moods);
  const aspects = diffSets(morphA.aspects, morphB.aspects);
  const walsCategories = diffSets(
    (morphA.tense_aspect_categories || []).map((c) => c.name),
    (morphB.tense_aspect_categories || []).map((c) => c.name),
  );
  const anyAvailable = [cases, tenses, moods, aspects, walsCategories].some((d) => d.score !== null);
  if (!anyAvailable) return { available: false };
  const scores = [cases, tenses, moods, aspects, walsCategories].map((d) => d.score).filter((s) => s !== null);
  const score = scores.reduce((sum, s) => sum + s, 0) / scores.length;
  return { available: true, cases, tenses, moods, aspects, walsCategories, score };
}

function compareWritingSystem(a, b) {
  const wsA = a.writing_system;
  const wsB = b.writing_system;
  if (!wsA && !wsB) return { available: false };
  if (!wsA || !wsB) return { available: true, wsA, wsB, score: null, note: "only one side has known data" };
  let score;
  if (wsA.script_name === wsB.script_name) score = 0;
  else if (wsA.script_type === wsB.script_type) score = 0.4;
  else score = 1;
  return { available: true, wsA, wsB, score };
}

/** Aggregates whichever per-category scores are available into one 0-100 overall score,
 * re-normalized over the categories that actually had data — see README.md's scoring design. */
function computeOverall(categories) {
  const weighted = [
    { key: "family", weight: 1.5 },
    { key: "phonology", weight: 1 },
    { key: "wordOrder", weight: 1 },
    { key: "morphology", weight: 1 },
    { key: "writingSystem", weight: 0.5 },
  ];
  let weightedSum = 0;
  let totalWeight = 0;
  let availableCount = 0;
  for (const { key, weight } of weighted) {
    const cat = categories[key];
    if (cat.available && cat.score !== null && cat.score !== undefined) {
      weightedSum += cat.score * weight;
      totalWeight += weight;
      availableCount++;
    }
  }
  if (totalWeight === 0) return { score: null, availableCount, totalCount: weighted.length };
  return { score: Math.round((weightedSum / totalWeight) * 100), availableCount, totalCount: weighted.length };
}

function qualitativeLabel(score) {
  if (score === null) return "not enough data";
  if (score < 15) return "very close";
  if (score < 35) return "close";
  if (score < 60) return "moderately different";
  if (score < 80) return "distant";
  return "very distant";
}

function compareLanguages(a, b) {
  const categories = {
    family: compareFamily(a, b),
    phonology: comparePhonology(a, b),
    wordOrder: compareWordOrder(a, b),
    morphology: compareMorphology(a, b),
    writingSystem: compareWritingSystem(a, b),
  };
  const overall = computeOverall(categories);
  return { a, b, categories, overall, label: qualitativeLabel(overall.score) };
}

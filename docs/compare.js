// Pure comparison functions: given two LanguageProfile objects (as fetched from
// data/languages/<glottocode>.json), compute a per-category comparison. No network calls, no
// LLM calls — everything here is plain arithmetic/set-logic over already-fetched JSON, per
// the project's core design constraint (see README.md).

/** Loose equality for classification-path node names: lowercased, hyphens/spaces stripped —
 * the same two sources can spell a family differently (confirmed live: Wikidata's
 * "Afroasiatic" vs. WALS's "Afro-Asiatic" for the same family). */
function normalizeFamilyName(name) {
  return name.toLowerCase().replace(/[-\s]/g, "");
}

/** Family/genealogical distance. Finds the DEEPEST name that appears in both classification
 * paths — not simply the longest matching *prefix* — because the two paths can come from
 * different sources at different granularity for perfectly valid reasons (see
 * build_profile.py: a language falls back to WALS's shallower 3-level classification when
 * its own Wikidata chain is too sparse to trust). Confirmed live: Levantine Arabic's path
 * (Wikidata, 4 levels, includes an explicit "Arabic" node) vs. Egyptian Arabic's (WALS
 * fallback, 3 levels, jumps straight from "Semitic" to the specific variety, no separate
 * "Arabic" node at all) — positional prefix-matching found them sharing only "Afro-Asiatic"+
 * "Semitic" misaligned by a hyphen and scored them as nearly unrelated; matching on the
 * deepest shared name regardless of position correctly finds "Semitic" as their closest
 * common ancestor in this data and scores them as close relatives. Works the same whether
 * either side is a "leaf" language or a "group" (family/macrolanguage) entity — a group's
 * path simply ends at itself. */
function compareFamily(a, b) {
  const pathA = a.classification.path.map((n) => n.name);
  const pathB = b.classification.path.map((n) => n.name);

  let bestIndexA = -1;
  let bestIndexB = -1;
  let bestDepth = -1;
  pathA.forEach((nameA, indexA) => {
    const normalizedA = normalizeFamilyName(nameA);
    pathB.forEach((nameB, indexB) => {
      if (normalizeFamilyName(nameB) !== normalizedA) return;
      if (indexA + indexB > bestDepth) {
        bestDepth = indexA + indexB;
        bestIndexA = indexA;
        bestIndexB = indexB;
      }
    });
  });

  // No shared name anywhere in either path means these two don't share so much as a single
  // ancestor in the data we have — that's the maximum this metric can express, full stop.
  // The hops/maxDepth formula below is only meaningful when a common ancestor exists; applying
  // it here too was a real bug: two completely unrelated languages with differently-sized
  // classification paths (e.g. one from a deep Wikidata chain, one from WALS's shallow
  // 3-level fallback) scored under 100 purely because of that length mismatch, not because
  // they shared anything — confirmed live, a pair sharing zero family nodes scored "distant"
  // instead of "very distant".
  if (bestIndexA === -1) {
    return {
      available: true,
      score: 1,
      pathA,
      pathB,
      commonAncestor: null,
      divergeAtA: pathA[0] ?? null,
      divergeAtB: pathB[0] ?? null,
    };
  }

  const hopsA = pathA.length - 1 - bestIndexA;
  const hopsB = pathB.length - 1 - bestIndexB;
  const maxDepth = Math.max(pathA.length, pathB.length, 1);
  const score = Math.min(1, (hopsA + hopsB) / (2 * maxDepth));
  return {
    available: true,
    score,
    pathA,
    pathB,
    commonAncestor: pathA[bestIndexA],
    divergeAtA: pathA[bestIndexA + 1] ?? null,
    divergeAtB: pathB[bestIndexB + 1] ?? null,
  };
}

/** Three-column shared/only-A/only-B split of two string lists (order-insensitive, de-duped).
 *
 * `score` is null whenever EITHER list is empty — not just when both are. An empty list here
 * always means "no data gathered for this side" (no real language has zero phonemes, and for
 * the Wikidata-sourced grammar lists we can't currently distinguish "confirmed zero" from
 * "not queried" — see README.md's to-do on this). Treating an empty side as "zero items,
 * maximally different from whatever the other side has" was a real bug: it made Levantine
 * Arabic (no PHOIBLE phoneme data) and Egyptian Arabic (67 phonemes) register as 100%
 * different in phonology alone, when they're actually close relatives. `shared`/`onlyA`/
 * `onlyB` are still returned so a caller *could* inspect them, but callers should treat a
 * null score as "not comparable" and avoid rendering a one-sided diff as if it meant
 * something — see app.js's category renderers. */
function diffSets(listA, listB) {
  const setA = new Set(listA || []);
  const setB = new Set(listB || []);
  const shared = [...setA].filter((x) => setB.has(x)).sort();
  const onlyA = [...setA].filter((x) => !setB.has(x)).sort();
  const onlyB = [...setB].filter((x) => !setA.has(x)).sort();
  const union = shared.length + onlyA.length + onlyB.length;
  const score = setA.size === 0 || setB.size === 0 ? null : 1 - shared.length / union; // Jaccard distance
  return { shared, onlyA, onlyB, score };
}

function comparePhonology(a, b) {
  const phonemesA = a.phonology?.phonemes || [];
  const phonemesB = b.phonology?.phonemes || [];
  if (phonemesA.length === 0 || phonemesB.length === 0) return { available: false };
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

/** A language can genuinely use more than one script (Japanese: hiragana+katakana+kanji;
 * several Arabic varieties: the Arabic script plus an informal Latin-based "chat alphabet")
 * — compared the same way as phonemes: a shared/only-in-A/only-in-B set over script names,
 * not a single name/type pair. Falls back to comparing script *types* only when neither side
 * shares an exact script name but their types overlap (e.g. two different Latin-alphabet
 * languages still both use "an alphabet", worth surfacing even if no single script matches). */
function compareWritingSystem(a, b) {
  const scriptsA = a.writing_system?.scripts || [];
  const scriptsB = b.writing_system?.scripts || [];
  if (scriptsA.length === 0 || scriptsB.length === 0) return { available: false };
  const namesDiff = diffSets(scriptsA.map((s) => s.name), scriptsB.map((s) => s.name));
  const typesA = new Set(scriptsA.map((s) => s.script_type));
  const typesB = new Set(scriptsB.map((s) => s.script_type));
  const sharedTypes = [...typesA].filter((t) => typesB.has(t));

  // Letter-level comparison (CLDR exemplar characters — see build_profile.py's
  // _attach_sample_glyphs) is far more informative than the name/type match above when both
  // sides have it: two scripts can be named completely differently ("French alphabet" vs.
  // "Italian alphabet" — no exact name match, so the diff above shows zero overlap) while
  // being almost entirely the same set of letters. Only ever set on at most one script entry
  // per profile (see that function's docstring), so "the" entry with glyphs, if any, is this
  // language's one unambiguous primary script.
  const glyphsA = scriptsA.find((s) => (s.sample_glyphs || []).length > 0)?.sample_glyphs;
  const glyphsB = scriptsB.find((s) => (s.sample_glyphs || []).length > 0)?.sample_glyphs;
  const glyphs = glyphsA && glyphsB ? diffSets(glyphsA, glyphsB) : null;

  let score = namesDiff.score;
  if (namesDiff.shared.length === 0 && sharedTypes.length > 0) score = 0.4;
  if (glyphs && glyphs.score !== null) score = glyphs.score;
  return { available: true, scriptsA, scriptsB, sharedTypes, glyphs, ...namesDiff, score };
}

/** Donor-language overlap — do these two languages share a similar borrowing history? Scored
 * the same way as phonemes/scripts (a shared/only-in-A/only-in-B set over donor-language
 * names), but deliberately kept OUT of the overall score (never added to computeOverall's
 * `weighted` list below) — shared or different borrowing history is a fact about contact and
 * history, not a measure of how structurally alike two languages are. Two languages could
 * share an identical donor profile (e.g. both heavily borrowed from English) while being
 * typologically nothing alike, or vice versa; folding that into "how close are these
 * languages" would conflate two different questions. Shown for context instead, alongside
 * each language's own borrowed_ratio/sample_size/source (see schema.VocabularyOrigin) —
 * `voA`/`voB` carry those through for the renderer, nothing here computes with them. */
function compareVocabularyOrigin(a, b) {
  const voA = a.vocabulary_origin;
  const voB = b.vocabulary_origin;
  if (!voA || !voB) return { available: false };
  const donorsA = voA.donor_languages || [];
  const donorsB = voB.donor_languages || [];

  // A language never lists itself as its own donor (why would it?), but if it directly
  // influenced the OTHER language in this very comparison, that's still a genuine point of
  // overlap between the two sides — without this, comparing e.g. Latin to French would show
  // "Latin" as a donor only-in-French's set, even though Latin IS the other language being
  // compared here, not some unrelated third language that merely happens to match.
  const matchesProfile = (donor, profile) =>
    (donor.glottocode && donor.glottocode === profile.glottocode) ||
    normalizeFamilyName(donor.name) === normalizeFamilyName(profile.name) ||
    normalizeFamilyName(donor.name) === normalizeFamilyName(profile.english_name);

  let namesA = donorsA.map((d) => d.name);
  let namesB = donorsB.map((d) => d.name);
  const bBorrowedFromA = donorsB.find((d) => matchesProfile(d, a));
  const aBorrowedFromB = donorsA.find((d) => matchesProfile(d, b));
  if (bBorrowedFromA && !namesA.includes(bBorrowedFromA.name)) namesA = [...namesA, bBorrowedFromA.name];
  if (aBorrowedFromB && !namesB.includes(aBorrowedFromB.name)) namesB = [...namesB, aBorrowedFromB.name];

  const donorsDiff = diffSets(namesA, namesB);
  return { available: true, voA, voB, ...donorsDiff };
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
    // Not in computeOverall's `weighted` list — see compareVocabularyOrigin's docstring for
    // why this is informational-only, never folded into the overall distance score.
    vocabularyOrigin: compareVocabularyOrigin(a, b),
  };
  const overall = computeOverall(categories);
  return { a, b, categories, overall, label: qualitativeLabel(overall.score) };
}

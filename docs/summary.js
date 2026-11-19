// Template-based narrative generator — plain string templates over the already-computed
// comparison facts, no LLM call at runtime (see README.md's core design constraint).

function buildSummary(comparison) {
  const { a, b, categories, overall, label } = comparison;
  const parts = [];

  const fam = categories.family;
  if (fam.commonAncestor) {
    parts.push(`${a.name} and ${b.name} share a common ancestor: ${fam.commonAncestor}.`);
  } else {
    parts.push(`${a.name} and ${b.name} belong to entirely different, unrelated language families.`);
  }

  const ws = categories.writingSystem;
  if (ws.available) {
    if (ws.shared.length > 0) {
      parts.push(
        ws.onlyA.length === 0 && ws.onlyB.length === 0
          ? `Both are written in the same script${ws.shared.length > 1 ? "s" : ""}: ${ws.shared.join(", ")}.`
          : `Both share the ${ws.shared.join(", ")} script, though each also uses at least one the other doesn't.`,
      );
    } else if (ws.sharedTypes?.length > 0) {
      parts.push(`They use different scripts, but both are a ${ws.sharedTypes.join("/")} system.`);
    } else {
      parts.push(`They use fundamentally different writing systems (${ws.scriptsA.map((s) => s.name).join(", ")} vs. ${ws.scriptsB.map((s) => s.name).join(", ")}).`);
    }
  }

  const order = categories.wordOrder;
  if (order.available) {
    const basicOrder = order.rows.find((r) => r.name.includes("Subject, Object and Verb"));
    if (basicOrder && basicOrder.valueA && basicOrder.valueB) {
      if (basicOrder.valueA === basicOrder.valueB) {
        parts.push(`Both languages use ${basicOrder.valueA} basic word order.`);
      } else {
        parts.push(`Basic word order differs: ${a.name} is typically ${basicOrder.valueA}, while ${b.name} is ${basicOrder.valueB}.`);
      }
    }
  }

  const phon = categories.phonology;
  if (phon.available && phon.score !== null) {
    const pct = Math.round((1 - phon.score) * 100);
    parts.push(`Their phoneme inventories overlap by about ${pct}% (${phon.shared.length} shared sounds out of ${phon.shared.length + phon.onlyA.length + phon.onlyB.length} total).`);
  }

  const vocab = categories.vocabularyOrigin;
  if (vocab.available) {
    const pctA = Math.round(vocab.voA.borrowed_ratio * 100);
    const pctB = Math.round(vocab.voB.borrowed_ratio * 100);
    parts.push(`An estimated ${pctA}% of ${a.name}'s vocabulary is borrowed, vs. ${pctB}% for ${b.name}.`);
    if (vocab.shared.length > 0) {
      parts.push(`Both show influence from ${vocab.shared.slice(0, 3).join(", ")}.`);
    }
  }

  if (overall.score !== null) {
    parts.push(`Overall linguistic distance: ${overall.score}/100 (${label}), based on ${overall.availableCount} of ${overall.totalCount} available metrics.`);
  } else {
    parts.push(`Not enough comparable data was available to compute an overall score for this pair.`);
  }

  return parts.join(" ");
}

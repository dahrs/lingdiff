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
  if (ws.available && ws.wsA && ws.wsB) {
    if (ws.wsA.script_name === ws.wsB.script_name) {
      parts.push(`Both are written in the ${ws.wsA.script_name}.`);
    } else if (ws.wsA.script_type === ws.wsB.script_type) {
      parts.push(`Both use a ${ws.wsA.script_type} writing system, but different scripts (${ws.wsA.script_name} vs. ${ws.wsB.script_name}).`);
    } else {
      parts.push(`They use fundamentally different writing systems: ${ws.wsA.script_name} (${ws.wsA.script_type}) vs. ${ws.wsB.script_name} (${ws.wsB.script_type}).`);
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

  if (overall.score !== null) {
    parts.push(`Overall linguistic distance: ${overall.score}/100 (${label}), based on ${overall.availableCount} of ${overall.totalCount} available metrics.`);
  } else {
    parts.push(`Not enough comparable data was available to compute an overall score for this pair.`);
  }

  return parts.join(" ");
}

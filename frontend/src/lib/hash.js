// Byte-identical reimplementation of backend evidence hashing (PRD 11.9):
// canonical JSON = json.dumps(obj, sort_keys=True, separators=(",", ":"),
// ensure_ascii=False); leaf = sha256(canonical); Merkle root duplicates the
// last hash on odd levels. All record keys/values here are ASCII str/int/bool,
// so this matches Python exactly.

export function canonicalJson(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "null";
    return Number.isInteger(value) ? String(value) : String(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(",")}}`;
}

export async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function merkleRoot(leafHexes) {
  if (leafHexes.length === 0) return sha256Hex("");
  let level = [...leafHexes];
  while (level.length > 1) {
    if (level.length % 2 === 1) level.push(level[level.length - 1]);
    const next = [];
    for (let i = 0; i < level.length; i += 2) {
      next.push(await sha256Hex(level[i] + level[i + 1]));
    }
    level = next;
  }
  return level[0];
}

// Recompute a report root from a pasted report payload (GET /api/reports/{id}).
// Returns { storedRoot, recomputedRoot, status, recordCount }.
export async function verifyPayload(payload) {
  const records = [...(payload?.evidence || [])].sort((a, b) => a.citation_id - b.citation_id);
  const leaves = [];
  for (const r of records) leaves.push(await sha256Hex(canonicalJson(r)));
  const recomputedRoot = await merkleRoot(leaves);
  const storedRoot = payload?.root_hash || null;
  return {
    storedRoot,
    recomputedRoot,
    status: storedRoot && storedRoot === recomputedRoot ? "MATCH" : "MISMATCH",
    recordCount: records.length,
  };
}

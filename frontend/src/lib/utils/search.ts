export const MAX_AUTOCOMPLETE_OPTIONS = 80;

/**
 * Case-fold, strip diacritics and collapse whitespace — mirrors the backend
 * dashboard's normalize_search_text so rankings feel consistent.
 */
export function normalizeSearchText(value: unknown): string {
  return String(value ?? '')
    .toLowerCase()
    .normalize('NFKD')
    // eslint-disable-next-line no-misleading-character-class
    .replace(/\p{Diacritic}/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function similarity(a: string, b: string): number {
  // Small Jaro-Winkler-style similarity so tiny typos still rank correctly
  // without pulling in a dependency.
  const A = a.slice(0, 6);
  const B = b.slice(0, 6);
  const len = Math.max(A.length, B.length, 1);
  let matches = 0;
  const minLen = Math.min(A.length, B.length);
  for (let i = 0; i < minLen; i++) {
    if (A[i] === B[i]) matches++;
  }
  const m = matches / len;
  return (m + m + m) / 3;
}

/**
 * Rank a list of options against a typed query the same way the legacy
 * Streamlit dashboard did: prefix matches first, then contains, then fuzzy.
 */
export function rankSearchOptions(query: string, options: string[], limit = MAX_AUTOCOMPLETE_OPTIONS): string[] {
  const queryKey = normalizeSearchText(query);
  if (!queryKey) return options.slice(0, limit);

  const keyed = options.map((option) => ({ option, key: normalizeSearchText(option) }));
  const startsWith: string[] = [];
  const contains: string[] = [];
  const fuzzy: string[] = [];

  for (const { option, key } of keyed) {
    if (key.startsWith(queryKey)) startsWith.push(option);
  }
  for (const { option, key } of keyed) {
    if (key.includes(queryKey) && !startsWith.includes(option)) contains.push(option);
  }
  const fuzzyScored = keyed
    .filter(({ option, key }) => !startsWith.includes(option) && !contains.includes(option))
    .map(({ option, key }) => ({ option, score: similarity(queryKey, key) }))
    .filter(({ score }) => score > 0.5)
    .sort((x, y) => y.score - x.score);
  for (const { option } of fuzzyScored) fuzzy.push(option);

  return [...new Set([...startsWith, ...contains, ...fuzzy])].slice(0, limit);
}

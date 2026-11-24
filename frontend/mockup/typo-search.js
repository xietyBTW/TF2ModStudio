/**
 * Поиск с опечатками в выпадающих списках - тем же правилом, что поиск
 * каталога в Python (src/shared/text_search.py): до трёх букв точно, с
 * четырёх одна опечатка, с восьми две, и ищется она в начале слов. Копии
 * сверяет tests/test_typo_search_parity_js.py
 */
export const typoBudget = (w) => (w.length < 4 ? 0 : w.length < 8 ? 1 : 2);

/** Правок до лучшего начала слова (Дамерау-Левенштейн), больше limit - limit + 1 */
export function prefixTypos(q, w, limit) {
  const n = q.length;
  const m = Math.min(w.length, n + limit);
  let before = [];
  let prev = Array.from({ length: m + 1 }, (_, j) => j);
  for (let i = 1; i <= n; i += 1) {
    const cur = [i];
    for (let j = 1; j <= m; j += 1) {
      let best = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (q[i - 1] !== w[j - 1]));
      if (i > 1 && j > 1 && q[i - 1] === w[j - 2] && q[i - 2] === w[j - 1]) {
        best = Math.min(best, before[j - 2] + 1);
      }
      cur.push(best);
    }
    if (Math.min(...cur) > limit) return limit + 1;
    [before, prev] = [prev, cur];
  }
  return Math.min(...prev);
}

/** Слова текста: «superrare_burning1» -> superrare, burning1 */
export const wordsOf = (text) => text.toLowerCase().replace(/ё/g, 'е')
  .split(/[^0-9a-zа-я]+/).filter(Boolean);

/** -1 - мимо, иначе сколько слов запроса нашлось только с опечаткой */
export function matchTypos(raw, words) {
  const text = raw.replace(/ё/g, 'е');
  const parts = wordsOf(text);
  let typos = 0;
  for (const word of words) {
    const q = word.replace(/ё/g, 'е');
    if (text.includes(q)) continue;
    const limit = typoBudget(q);
    if (limit && parts.some((w) => prefixTypos(q, w, limit) <= limit)) {
      typos += 1;
      continue;
    }
    return -1;
  }
  return typos;
}

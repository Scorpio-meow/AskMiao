(() => {
  const PY_WHITESPACE = '\\t-\\r\\x1c-\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
  const PY_STRIP = new RegExp(`^[${PY_WHITESPACE}]+|[${PY_WHITESPACE}]+$`, 'g');
  const WHOOSH_BM25F = { B: 0.75, K1: 1.2 };
  const WHOOSH_LENGTH_BYTES = 256;
  const WHOOSH_LENGTH_CAP = 106374;
  const WHOOSH_LENGTH_BASE = 1.033;
  const WHOOSH_LENGTH_SCALE = 27;

  const length = (text) => {
    let count = 0;
    for (const _ of text) count += 1;
    return count;
  };
  const pyRound = (value) => {
    const floor = Math.floor(value);
    const diff = value - floor;
    if (diff > 0.5) return floor + 1;
    if (diff < 0.5) return floor;
    return floor % 2 === 0 ? floor : floor + 1;
  };

  const createSplitter = ({ chunkSize, chunkOverlap, separators }) => {
    const join = (pieces) => {
      const text = pieces.join('').replace(PY_STRIP, '');
      return text || null;
    };
    const merge = (splits) => {
      const docs = [];
      let current = [];
      let total = 0;
      splits.forEach((piece) => {
        const size = length(piece);
        if (total + size > chunkSize && current.length > 0) {
          const doc = join(current);
          if (doc !== null) docs.push(doc);
          while (total > chunkOverlap || (total + size > chunkSize && total > 0)) {
            total -= length(current[0]);
            current = current.slice(1);
          }
        }
        current.push(piece);
        total += size;
      });
      const doc = join(current);
      if (doc !== null) docs.push(doc);
      return docs;
    };
    const splitOn = (text, separator) => {
      if (!separator) return Array.from(text);
      const parts = text.split(separator);
      return [parts[0], ...parts.slice(1).map((part) => separator + part)].filter((piece) => piece);
    };
    const recurse = (text, list) => {
      const chunks = [];
      let separator = list[list.length - 1];
      let rest = [];
      for (let index = 0; index < list.length; index += 1) {
        const candidate = list[index];
        if (!candidate) {
          separator = candidate;
          break;
        }
        if (text.includes(candidate)) {
          separator = candidate;
          rest = list.slice(index + 1);
          break;
        }
      }
      let good = [];
      splitOn(text, separator).forEach((piece) => {
        if (length(piece) < chunkSize) {
          good.push(piece);
          return;
        }
        if (good.length) {
          chunks.push(...merge(good));
          good = [];
        }
        if (rest.length) chunks.push(...recurse(piece, rest));
        else chunks.push(piece);
      });
      if (good.length) chunks.push(...merge(good));
      return chunks;
    };
    return (text) => recurse(text, separators);
  };

  const LENGTH_TABLE = Array.from({ length: WHOOSH_LENGTH_BYTES }, (_, index) => pyRound((WHOOSH_LENGTH_BASE ** index - 1) * WHOOSH_LENGTH_SCALE));
  const quantizedLength = (value) => {
    if (value >= WHOOSH_LENGTH_CAP) return LENGTH_TABLE[WHOOSH_LENGTH_BYTES - 1];
    let low = 0;
    let high = LENGTH_TABLE.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (LENGTH_TABLE[middle] < value) low = middle + 1;
      else high = middle;
    }
    return LENGTH_TABLE[low];
  };

  const createKeywordIndex = (texts, { hanRun, hanNgramSizes }) => {
    const ngrams = (text, size) => {
      const tokens = [];
      for (const match of text.matchAll(new RegExp(hanRun, 'gu'))) {
        const run = Array.from(match[0]);
        for (let start = 0; start + size <= run.length; start += 1) tokens.push(run.slice(start, start + size).join(''));
      }
      return tokens;
    };
    const fields = hanNgramSizes.map((size) => {
      const docs = texts.map((text) => {
        const counts = new Map();
        const tokens = ngrams(text, size);
        tokens.forEach((token) => counts.set(token, (counts.get(token) ?? 0) + 1));
        return { counts, length: tokens.length };
      });
      const frequency = new Map();
      docs.forEach((doc) => doc.counts.forEach((_, token) => frequency.set(token, (frequency.get(token) ?? 0) + 1)));
      const total = docs.reduce((sum, doc) => sum + doc.length, 0);
      return { size, docs, frequency, average: total / (texts.length || 1) || 1 };
    });
    const search = (query) => {
      const scores = texts.map(() => 0);
      const matched = texts.map(() => new Set());
      const terms = [];
      fields.forEach((field) => {
        const unique = Array.from(new Set(ngrams(query, field.size)));
        unique.forEach((term) => {
          terms.push(term);
          const n = field.frequency.get(term) ?? 0;
          if (!n) return;
          const idf = Math.log(texts.length / (n + 1)) + 1;
          field.docs.forEach((doc, index) => {
            const tf = doc.counts.get(term);
            if (!tf) return;
            const fl = quantizedLength(doc.length);
            const { B, K1 } = WHOOSH_BM25F;
            scores[index] += idf * ((tf * (K1 + 1)) / (tf + K1 * ((1 - B) + B * fl / field.average)));
            matched[index].add(term);
          });
        });
      });
      const hits = scores
        .map((score, index) => ({ index, score, terms: Array.from(matched[index]) }))
        .filter((hit) => hit.terms.length > 0)
        .sort((a, b) => b.score - a.score || a.index - b.index);
      return { hits, terms };
    };
    return { search };
  };

  window.askmiaoLab = Object.freeze({ createSplitter, createKeywordIndex, length });
})();
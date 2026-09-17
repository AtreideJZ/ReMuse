/** 搜索历史（T4.2）：localStorage 存最近 8 条查询词，仅本地，不涉及后端。 */

const STORAGE_KEY = "remuse-search-history";
const MAX_ENTRIES = 8;

export function readSearchHistory(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // 宽松校验：只保留非空字符串
    return parsed.filter(
      (q): q is string => typeof q === "string" && q.trim().length > 0,
    );
  } catch {
    return [];
  }
}

function writeSearchHistory(items: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // localStorage 不可用时忽略
  }
}

/** 记录一次查询：去重置顶、截断到最近 8 条；返回最新列表。 */
export function addSearchHistory(query: string): string[] {
  const q = query.trim();
  const rest = readSearchHistory().filter((item) => item !== q);
  const next = (q ? [q, ...rest] : rest).slice(0, MAX_ENTRIES);
  writeSearchHistory(next);
  return next;
}

export function removeSearchHistory(query: string): string[] {
  const next = readSearchHistory().filter((item) => item !== query);
  writeSearchHistory(next);
  return next;
}

export function clearSearchHistory(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // localStorage 不可用时忽略
  }
}

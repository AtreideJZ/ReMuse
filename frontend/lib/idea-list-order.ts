/*
 * 列表顺序快照（T4.5）：把列表当前顺序（id + 标题）存入 sessionStorage，
 * 详情页据此提供「上一条 / 下一条」顺序浏览。sessionStorage 随标签页关闭即失效，
 * 与「列表顺序只对当次浏览会话有意义」的语义一致。
 */
import type { Idea } from "./types";
import { truncate } from "./time";

const STORAGE_KEY = "remuse-list-order";
const MAX_ENTRIES = 200;

export interface ListOrderEntry {
  id: string;
  title: string;
}

/** 标题口径与 IdeaCard 一致：AI 完成用 ai_title，否则用原文截断。 */
export function ideaListTitle(idea: Idea): string {
  return idea.ai_status === "done" && idea.ai_title
    ? idea.ai_title
    : truncate(idea.raw_content, 30);
}

export function writeIdeaListOrder(ideas: Idea[]): void {
  try {
    const entries: ListOrderEntry[] = ideas
      .slice(0, MAX_ENTRIES)
      .map((idea) => ({ id: idea.id, title: ideaListTitle(idea) }));
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // sessionStorage 不可用时忽略
  }
}

export function readIdeaListOrder(): ListOrderEntry[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // 宽松校验：只保留形状正确的条目
    return parsed.filter(
      (e): e is ListOrderEntry =>
        e !== null &&
        typeof e === "object" &&
        typeof (e as ListOrderEntry).id === "string" &&
        typeof (e as ListOrderEntry).title === "string",
    );
  } catch {
    return [];
  }
}

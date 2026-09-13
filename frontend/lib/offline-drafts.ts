/** 离线草稿队列（AC-F013-02）：断网时保存灵感，恢复联网后自动补发同步。 */

export interface OfflineDraft {
  content: string;
  project_id: string | null;
  saved_at: string;
}

const STORAGE_KEY = "remuse-offline-drafts";

export function readDrafts(): OfflineDraft[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // 宽松校验：只保留形状正确的条目
    return parsed.filter(
      (d): d is OfflineDraft =>
        d !== null &&
        typeof d === "object" &&
        typeof (d as OfflineDraft).content === "string" &&
        typeof (d as OfflineDraft).saved_at === "string"
    );
  } catch {
    return [];
  }
}

function writeDrafts(drafts: OfflineDraft[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts));
}

export function addDraft(content: string, projectId: string | null): OfflineDraft[] {
  const drafts = readDrafts();
  drafts.push({
    content,
    project_id: projectId,
    saved_at: new Date().toISOString(),
  });
  writeDrafts(drafts);
  return drafts;
}

/** 从队列中移除指定下标的草稿（补发成功后调用）。 */
export function removeDraftAt(index: number): OfflineDraft[] {
  const drafts = readDrafts();
  drafts.splice(index, 1);
  writeDrafts(drafts);
  return drafts;
}

/** 当前待同步草稿数。 */
export function draftCount(): number {
  return readDrafts().length;
}

/*
 * 输入即存快照（T2.2）：单条、正在编辑中的内容，key 独立于上方待上传队列。
 * 队列语义是「保存失败待补发」，快照语义是「还没点保存」；混用会导致重复提交。
 */
const CAPTURE_DRAFT_KEY = "remuse-capture-draft";

/** 读取未提交快照；无或异常时返回空串。 */
export function readCaptureDraft(): string {
  try {
    return localStorage.getItem(CAPTURE_DRAFT_KEY) ?? "";
  } catch {
    return "";
  }
}

/** 写入快照；内容为空白时转为清除，避免残留空快照。 */
export function writeCaptureDraft(content: string): void {
  try {
    if (content.trim().length > 0) {
      localStorage.setItem(CAPTURE_DRAFT_KEY, content);
    } else {
      localStorage.removeItem(CAPTURE_DRAFT_KEY);
    }
  } catch {
    // localStorage 不可用时忽略
  }
}

export function clearCaptureDraft(): void {
  try {
    localStorage.removeItem(CAPTURE_DRAFT_KEY);
  } catch {
    // localStorage 不可用时忽略
  }
}

import type {
  AgentLogListParams,
  AgentLogListResponse,
  AgentNameListResponse,
  ApiKey,
  ApiKeyCreateBody,
  ApiKeyListResponse,
  ApiKeyWithSecret,
  Idea,
  IdeaListResponse,
  IdeaPatch,
  Project,
  ProjectListResponse,
  ProjectPatch,
  ReuseStats,
  ReuseTrace,
  SearchIdeaParams,
  SearchIdeasResult,
  TagListResponse,
} from "./types";

const DEFAULT_TIMEOUT_MS = 15000;

export const ADMIN_TOKEN_KEY = "remuse_admin_token";
export const AUTH_REQUIRED_EVENT = "remuse:auth-required";

/** 读取管理令牌（SSR 环境无 localStorage，返回 null） */
export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ADMIN_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAdminToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ADMIN_TOKEN_KEY, token);
  } catch {
    // localStorage 不可用时忽略
  }
}

export function clearAdminToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    // localStorage 不可用时忽略
  }
}

/** 管理令牌失效：清除本地令牌并广播事件，TokenGate 据此回到输入态 */
function notifyAuthRequired(): void {
  clearAdminToken();
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
}

export class ApiError extends Error {
  readonly status: number;
  /** 请求被调用方主动取消（如筛选变更取消在途请求），页面应静默忽略 */
  readonly aborted: boolean;

  constructor(status: number, message: string, options?: { aborted?: boolean }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.aborted = options?.aborted ?? false;
  }
}

/** 从错误响应构造 ApiError；401 或 503（未配置 ADMIN_TOKEN）时广播令牌失效 */
async function responseError(res: Response): Promise<ApiError> {
  let message = `请求失败（HTTP ${res.status}）`;
  let detail: string | null = null;
  try {
    const data: unknown = await res.json();
    if (data !== null && typeof data === "object" && "detail" in data) {
      const d = (data as { detail: unknown }).detail;
      if (typeof d === "string" && d.length > 0) {
        message = d;
        detail = d;
      }
    }
  } catch {
    // 保留默认错误信息
  }
  if (
    res.status === 401 ||
    (res.status === 503 && detail !== null && detail.includes("ADMIN_TOKEN"))
  ) {
    notifyAuthRequired();
  }
  return new ApiError(res.status, message);
}

/** 底层 fetch：注入 X-Admin-Token、默认 15s 超时、合并调用方 signal、统一错误处理 */
async function rawFetch(path: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, DEFAULT_TIMEOUT_MS);
  const callerSignal = init?.signal ?? undefined;
  const onCallerAbort = () => controller.abort();
  if (callerSignal) {
    if (callerSignal.aborted) {
      controller.abort();
    } else {
      callerSignal.addEventListener("abort", onCallerAbort);
    }
  }

  // 无 body 的请求（GET/DELETE、无参 POST）不带 Content-Type
  const hasBody = init?.body !== undefined && init?.body !== null;
  const headers: Record<string, string> = hasBody
    ? { "Content-Type": "application/json" }
    : {};
  const token = getAdminToken();
  if (token) {
    headers["X-Admin-Token"] = token;
  }

  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch {
    if (timedOut) {
      throw new ApiError(0, "请求超时，请检查网络或后端服务状态");
    }
    if (callerSignal?.aborted || controller.signal.aborted) {
      throw new ApiError(0, "请求已取消", { aborted: true });
    }
    throw new ApiError(0, "无法连接到服务器，请确认后端服务已启动");
  } finally {
    clearTimeout(timeout);
    if (callerSignal) {
      callerSignal.removeEventListener("abort", onCallerAbort);
    }
  }

  if (!res.ok) {
    throw await responseError(res);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await rawFetch(path, init);
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export interface IdeaListParams {
  project_id?: string;
  tag?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  createIdea(
    content: string,
    projectId?: string | null,
    capturedAt?: string | null,
  ): Promise<Idea> {
    return request<Idea>("/api/ideas", {
      method: "POST",
      body: JSON.stringify({
        content,
        project_id: projectId ?? null,
        captured_at: capturedAt ?? null,
      }),
    });
  },

  listIdeas(params: IdeaListParams = {}): Promise<IdeaListResponse> {
    const q = new URLSearchParams();
    if (params.project_id) q.set("project_id", params.project_id);
    if (params.tag) q.set("tag", params.tag);
    if (params.status) q.set("status", params.status);
    q.set("limit", String(params.limit ?? 50));
    q.set("offset", String(params.offset ?? 0));
    return request<IdeaListResponse>(`/api/ideas?${q.toString()}`);
  },

  getIdea(id: string): Promise<Idea> {
    return request<Idea>(`/api/ideas/${id}`);
  },

  updateIdea(id: string, patch: IdeaPatch): Promise<Idea> {
    return request<Idea>(`/api/ideas/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  deleteIdea(id: string): Promise<void> {
    return request<void>(`/api/ideas/${id}`, { method: "DELETE" });
  },

  retryIdeaAI(id: string): Promise<Idea> {
    return request<Idea>(`/api/ideas/${id}/retry-ai`, { method: "POST" });
  },

  /** 相关灵感（向量相似）；目标无 embedding 时后端返回空数组 */
  getRelatedIdeas(id: string, limit = 5): Promise<Idea[]> {
    const q = new URLSearchParams({ limit: String(limit) });
    return request<Idea[]>(`/api/ideas/${id}/related?${q.toString()}`);
  },

  /** 复用档案：累计检索次数 + 命中明细时间线 */
  getReuseTrace(id: string): Promise<ReuseTrace> {
    return request<ReuseTrace>(`/api/ideas/${id}/reuse-trace`);
  },

  listProjects(): Promise<ProjectListResponse> {
    return request<ProjectListResponse>("/api/projects");
  },

  createProject(name: string, description?: string): Promise<Project> {
    return request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, description: description ?? "" }),
    });
  },

  updateProject(id: string, patch: ProjectPatch): Promise<Project> {
    return request<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  deleteProject(id: string): Promise<void> {
    return request<void>(`/api/projects/${id}`, { method: "DELETE" });
  },

  listTags(): Promise<TagListResponse> {
    return request<TagListResponse>("/api/tags");
  },

  /** 语义搜索（E7：响应含 items + 零结果时的 near_miss）。可透传 signal 取消在途请求。 */
  searchIdeas(
    params: SearchIdeaParams,
    signal?: AbortSignal,
  ): Promise<SearchIdeasResult> {
    const q = new URLSearchParams();
    q.set("q", params.q);
    if (params.project_id) q.set("project_id", params.project_id);
    if (params.tag) q.set("tag", params.tag);
    if (params.days !== undefined) q.set("days", String(params.days));
    q.set("limit", String(params.limit ?? 20));
    return request<SearchIdeasResult>(`/api/search/ideas?${q.toString()}`, {
      signal,
    });
  },

  listKeys(): Promise<ApiKeyListResponse> {
    return request<ApiKeyListResponse>("/api/keys");
  },

  createKey(body: ApiKeyCreateBody): Promise<ApiKeyWithSecret> {
    return request<ApiKeyWithSecret>("/api/keys", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  revokeKey(id: string): Promise<ApiKey> {
    return request<ApiKey>(`/api/keys/${id}/revoke`, { method: "POST" });
  },

  listAgentLogs(params: AgentLogListParams = {}): Promise<AgentLogListResponse> {
    const q = new URLSearchParams();
    if (params.agent_name) q.set("agent_name", params.agent_name);
    if (params.tool_name) q.set("tool_name", params.tool_name);
    if (params.days !== undefined) q.set("days", String(params.days));
    q.set("limit", String(params.limit ?? 50));
    q.set("offset", String(params.offset ?? 0));
    return request<AgentLogListResponse>(`/api/agent-logs?${q.toString()}`);
  },

  listAgentNames(): Promise<AgentNameListResponse> {
    return request<AgentNameListResponse>("/api/agent-logs/agents");
  },

  getReuseStats(): Promise<ReuseStats> {
    return request<ReuseStats>("/api/stats/reuse");
  },

  /** 全量数据导出，返回 Blob（调用方负责触发下载） */
  exportData(): Promise<Blob> {
    return rawFetch("/api/export").then((res) => res.blob());
  },
};

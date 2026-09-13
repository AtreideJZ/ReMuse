export type AIStatus = "pending" | "processing" | "done" | "failed";

export type IdeaStatus = "captured" | "retrieved" | "used" | "merged" | "dropped";

export type IdeaSource = "web" | "pwa" | "mcp";

export interface Idea {
  id: string;
  raw_content: string;
  ai_title: string | null;
  ai_summary: string | null;
  ai_maturity: string | null;
  ai_key_assumption: string | null;
  ai_confidence: number | null;
  ai_status: AIStatus;
  ai_error: string | null;
  ai_suggested_project: string | null;
  source: IdeaSource;
  status: IdeaStatus;
  importance: number;
  project_id: string | null;
  project_name: string | null;
  tags: string[];
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  idea_count: number;
  created_at: string;
}

export interface TagItem {
  name: string;
  count: number;
}

export interface IdeaListResponse {
  items: Idea[];
  total: number;
}

export interface ProjectListResponse {
  items: Project[];
}

export interface TagListResponse {
  items: TagItem[];
}

export interface IdeaPatch {
  project_id?: string | null;
  status?: IdeaStatus;
  importance?: number;
  ai_title?: string;
  ai_summary?: string;
}

export interface ProjectPatch {
  name?: string;
  description?: string;
}

export type ApiKeyScope = "read" | "write";

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: ApiKeyScope[];
  project_ids: string[];
  created_at: string;
  revoked_at: string | null;
}

/** 创建密钥时的响应，完整密钥仅此一次返回。 */
export interface ApiKeyWithSecret extends ApiKey {
  key: string;
}

export interface ApiKeyListResponse {
  items: ApiKey[];
}

export interface ApiKeyCreateBody {
  name: string;
  scopes: ApiKeyScope[];
  project_ids: string[];
}

export interface SearchIdeaParams {
  q: string;
  project_id?: string;
  tag?: string;
  /** 仅最近 N 天 */
  days?: number;
  limit?: number;
}

export type AgentLogStatus = "ok" | "denied" | "error";

export interface AgentLog {
  id: string;
  agent_name: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  returned_idea_ids: string[];
  status: AgentLogStatus;
  error: string | null;
  created_at: string;
}

export interface AgentLogListResponse {
  items: AgentLog[];
  total: number;
}

export interface AgentNameListResponse {
  items: string[];
}

export interface AgentLogListParams {
  agent_name?: string;
  tool_name?: string;
  /** 仅最近 N 天 */
  days?: number;
  limit?: number;
  offset?: number;
}

/** 复用率统计：reuse_rate = (used + merged) / total_ideas（dropped 已由后端排除） */
export interface ReuseStats {
  total_ideas: number;
  used: number;
  merged: number;
  retrieved: number;
  captured: number;
  reuse_rate: number;
}

/** 复用档案的明细事件（来自 agent_call_logs，保留期清理后 events 可能少于累计次数） */
export interface ReuseTraceEvent {
  at: string;
  agent_name: string;
  tool_name: string;
}

/** 单条灵感的复用档案：retrieved_count 为冗余累计列，不受日志保留期影响 */
export interface ReuseTrace {
  status: string;
  retrieved_count: number;
  last_retrieved_at: string | null;
  events: ReuseTraceEvent[];
}

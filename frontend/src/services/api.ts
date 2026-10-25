import axios, { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { isTokenExpired, clearAuth } from '../utils/tokenUtils.ts';
import { devWarn } from '../utils/secureLogger.ts';
import { createSseParser } from './sse.ts';
export interface ChatAttachment {
  id?: string;
  filename: string;
  file_type: string;
  file_size?: number;
  data_url?: string;
  content?: string;
  file?: File;
}
export interface Message {
  id?: number;
  content: string;
  is_user: boolean;
  created_at?: string;
  context_used?: string | null | string[];
  model_name?: string | null;
  reasoning_effort?: string | null;
  attachments?: ChatAttachment[];
  sources?: string[];
  sources_detail?: Array<{
    source: string;
    chunk?: number;
    score?: number | null;
    snippet?: string;
    url?: string;
    citation?: number;
  }>;
  research_trace?: Array<{
    step: number;
    tool: string;
    arguments?: unknown;
    output_preview?: unknown;
    duration_seconds?: number;
    status?: string;
  }>;
  think?: string | null;
  role?: string;
  isUser?: boolean;
  /** 僅前端使用：串流失敗時的錯誤訊息 */
  error?: string;
  /** 僅前端使用：使用者手動停止產生 */
  stopped?: boolean;
  /** 僅前端使用：Agent 暫停等待使用者核准的工具呼叫 */
  pending_approval?: PendingToolApproval | null;
}
export interface PendingToolApproval {
  approval_id: string;
  step: number;
  tool: string;
  tool_display_name: string;
  // 實際送出的位置：自訂 API 工具為「方法 主機」，MCP 為傳輸方式與主機或指令
  target: string;
  arguments?: unknown;
}
export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}
export interface User {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  role: string;
}
const RAW_API_URL = (import.meta.env.VITE_API_BASE as string) || (import.meta.env.VITE_API_URL as string) || '/api';
const ensureTrailingApi = (urlString: string): string => {
  const trimmed = urlString.replace(/\/+$/, '');
  return trimmed.endsWith('/api') ? trimmed : `${trimmed}/api`;
};
const normalizeAbsoluteUrl = (rawUrl: string): string => {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.hostname.includes('devtunnels.ms') && parsed.port) {
      devWarn('[api] Dropping explicit port from DevTunnels URL to avoid double port issues.', parsed.href);
      parsed.port = '';
    }
    const normalizedPath = ensureTrailingApi(parsed.pathname || '/api');
    parsed.pathname = normalizedPath;
    return parsed.toString().replace(/\/+$/, '');
  } catch (error) {
    devWarn('[api] Failed to parse API base URL, falling back to string normalization.', error);
    return ensureTrailingApi(rawUrl);
  }
};
const API_BASE_URL = RAW_API_URL.startsWith('http://') || RAW_API_URL.startsWith('https://')
  ? normalizeAbsoluteUrl(RAW_API_URL)
  : ensureTrailingApi(RAW_API_URL);
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});
// 同一時間只送一個換發請求：重新整理權杖只能用一次，同時送出的第二個請求會被拒絕並把使用者登出
let refreshPromise: Promise<string> | null = null;
const refreshAccessToken = (): Promise<string> => {
  refreshPromise ??= axios
    .post<{ access_token: string }>(`${API_BASE_URL}/auth/refresh`, {}, { withCredentials: true })
    .then((response) => {
      localStorage.setItem('access_token', response.data.access_token);
      return response.data.access_token;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
};
// 存取權杖已過期或 5 分鐘內到期時先換發；換發被拒（401）代表重新整理權杖也已失效
const currentAccessToken = async (): Promise<string | null> => {
  const token = localStorage.getItem('access_token');
  if (!token || !isTokenExpired(token, 300)) return token;
  try {
    return await refreshAccessToken();
  } catch (error: any) {
    devWarn('[Token] 靜默刷新失敗:', error.response?.status);
    if (error.response?.status === 401) {
      clearAuth();
      return null;
    }
    return token;
  }
};
const refreshOrSignOut = async (): Promise<string> => {
  try {
    return await refreshAccessToken();
  } catch (refreshError: any) {
    console.warn('[Token] Token 刷新失敗，清除認證信息:', refreshError.response?.status);
    clearAuth();
    const currentPath = window.location.pathname;
    if (currentPath !== '/login' && currentPath !== '/register') {
      setTimeout(() => {
        window.location.href = '/login';
      }, 100);
    }
    throw refreshError;
  }
};
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await currentAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);
// 這些端點回 401 代表帳密或 refresh token 本身無效，不應再觸發 refresh，否則原本的錯誤訊息會被蓋掉
const AUTH_PATHS_WITHOUT_REFRESH = ['/auth/login', '/auth/register', '/auth/refresh'];
const isAuthPathWithoutRefresh = (url?: string): boolean => {
  if (!url) return false;
  const path = url.split('?')[0];
  return AUTH_PATHS_WITHOUT_REFRESH.some((authPath) => path.endsWith(authPath));
};
api.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthPathWithoutRefresh(originalRequest.url)) {
      originalRequest._retry = true;
      const accessToken = await refreshOrSignOut();
      originalRequest.headers.Authorization = `Bearer ${accessToken}`;
      return api(originalRequest);
    }
    return Promise.reject(error);
  }
);
export interface StreamEvent {
  event: 'start' | 'step_start' | 'step_end' | 'approval_required' | 'approval_resolved' | 'token' | 'think' | 'sources' | 'done' | 'error';
  data: any;
}
export const chatService = {
  async sendMessageStream(
    content: string,
    conversationId: number | null = null,
    model_name: string | null = null,
    reasoning_effort: string = 'medium',
    onEvent: (event: StreamEvent) => void,
    signal?: AbortSignal,
    attachments?: ChatAttachment[]
  ): Promise<void> {
    const payloadAttachments = attachments?.map(a => ({
      filename: a.filename,
      file_type: a.file_type,
      file_size: a.file_size,
      data_url: a.data_url,
      content: a.content
    })) || [];
    const body = JSON.stringify({
      content,
      conversation_id: conversationId,
      model_name,
      reasoning_effort,
      attachments: payloadAttachments
    });
    // fetch 不經過 axios 攔截器，換發權杖要自己處理：過期的權杖連同附件送出只會換來 401 或 413
    const send = (token: string | null) => fetch(`${API_BASE_URL}/chat/send`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body,
      signal
    });
    let response = await send(await currentAccessToken());
    if (response.status === 401) {
      // 權杖在送出途中到期或已被撤銷：換發一次再重送
      response = await send(await refreshOrSignOut());
    }
    if (!response.ok) {
      const errText = await response.text();
      let detail = errText;
      try {
        const parsed = JSON.parse(errText);
        // 欄位驗證失敗（例如附件過大或數量過多）時 detail 是錯誤清單，取出每一項的說明
        detail = Array.isArray(parsed.detail)
          ? parsed.detail.map((item: { msg?: string }) => (item.msg || '').replace(/^Value error, /, '')).filter(Boolean).join('；')
          : parsed.detail || errText;
      } catch (e) {
      }
      throw new Error(detail || `HTTP Error ${response.status}`);
    }
    if (!response.body) {
      throw new Error('ReadableStream not supported by browser');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    const parser = createSseParser(({ event, data }) => {
      let parsedData: unknown;
      try {
        parsedData = JSON.parse(data);
      } catch (e) {
        console.warn('Failed to parse SSE data:', data, e);
        return;
      }
      onEvent({ event: event as StreamEvent['event'], data: parsedData });
    });
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
  },
  async getConversations(): Promise<Conversation[]> {
    const response = await api.get<Conversation[]>('/chat/conversations');
    return response.data;
  },
  async getConversation(conversationId: number): Promise<Conversation> {
    const response = await api.get<Conversation>(`/chat/conversations/${conversationId}`);
    return response.data;
  },
  async deleteConversation(conversationId: number): Promise<{ message: string }> {
    const response = await api.delete<{ message: string }>(`/chat/conversations/${conversationId}`);
    return response.data;
  },
  async getTools(): Promise<{ status: string; tools: any[] }> {
    const response = await api.get<{ status: string; tools: any[] }>('/chat/tools');
    return response.data;
  },
  async resolveApproval(approvalId: string, approved: boolean): Promise<{ approval_id: string; approved: boolean }> {
    const response = await api.post<{ approval_id: string; approved: boolean }>(
      `/chat/approvals/${encodeURIComponent(approvalId)}`,
      { approved }
    );
    return response.data;
  }
};
export const documentService = {
  async uploadDocument(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<any>('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  async uploadDocuments(files: File[]): Promise<any> {
    const formData = new FormData();
    files.forEach((f) => formData.append('file', f));
    const response = await api.post<any>('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  async getDocuments(): Promise<any[]> {
    const response = await api.get<any[]>('/documents/');
    return response.data;
  },
  async deleteDocument(documentId: number): Promise<any> {
    const response = await api.delete<any>(`/documents/${documentId}`);
    return response.data;
  }
};
export const adminService = {
  async getUsers(): Promise<User[]> {
    const response = await api.get<User[]>('/admin/users');
    return response.data;
  },
  async getStatistics(): Promise<any> {
    const response = await api.get<any>('/admin/statistics');
    return response.data;
  },
  async updateUser(userId: number, userData: Partial<User>): Promise<User> {
    const response = await api.put<User>(`/admin/users/${userId}`, userData);
    return response.data;
  },
  async deleteUser(userId: number): Promise<any> {
    const response = await api.delete<any>(`/admin/users/${userId}`);
    return response.data;
  }
};
export interface CustomApiToolItem {
  id: number;
  name: string;
  display_name: string;
  description: string;
  category: string;
  method: string;
  url: string;
  base_url?: string | null;
  path?: string | null;
  headers?: Record<string, string> | null;
  auth_type: string;
  auth_config?: Record<string, any> | null;
  parameters_schema?: Record<string, any> | null;
  request_body_schema?: Record<string, any> | null;
  param_locations?: Record<string, string> | null;
  response_mapping?: string | null;
  is_enabled: boolean;
  requires_approval: boolean;
  timeout: number;
  spec_version?: string | null;
  created_at: string;
  updated_at: string;
}
export const apiToolService = {
  async parseOpenApiSpec(spec_content_or_url: string, default_base_url?: string): Promise<{ status: string; data: any }> {
    const response = await api.post<{ status: string; data: any }>('/api-tools/parse-spec', {
      spec_content_or_url,
      default_base_url,
    });
    return response.data;
  },
  async importTools(importData: {
    tools: any[];
    global_base_url?: string;
    global_headers?: Record<string, string>;
    global_auth_type?: string;
    global_auth_config?: Record<string, any>;
  }): Promise<{ status: string; message: string; imported: number; updated: number }> {
    const response = await api.post<{ status: string; message: string; imported: number; updated: number }>(
      '/api-tools/import',
      importData
    );
    return response.data;
  },
  async getTools(params?: { category?: string; is_enabled?: boolean; search?: string }): Promise<{ status: string; total: number; tools: CustomApiToolItem[] }> {
    const response = await api.get<{ status: string; total: number; tools: CustomApiToolItem[] }>('/api-tools', {
      params,
    });
    return response.data;
  },
  async createTool(toolData: any): Promise<{ status: string; message: string; tool: CustomApiToolItem }> {
    const response = await api.post<{ status: string; message: string; tool: CustomApiToolItem }>(
      '/api-tools',
      toolData
    );
    return response.data;
  },
  async updateTool(toolId: number, toolData: any): Promise<{ status: string; message: string; tool: CustomApiToolItem }> {
    const response = await api.put<{ status: string; message: string; tool: CustomApiToolItem }>(
      `/api-tools/${toolId}`,
      toolData
    );
    return response.data;
  },
  async toggleTool(toolId: number): Promise<{ status: string; is_enabled: boolean; message: string }> {
    const response = await api.patch<{ status: string; is_enabled: boolean; message: string }>(
      `/api-tools/${toolId}/toggle`
    );
    return response.data;
  },
  async deleteTool(toolId: number): Promise<{ status: string; message: string }> {
    const response = await api.delete<{ status: string; message: string }>(`/api-tools/${toolId}`);
    return response.data;
  },
  async testTool(toolId: number, argumentsData: Record<string, any>): Promise<{ status: string; tool_name: string; result: any }> {
    const response = await api.post<{ status: string; tool_name: string; result: any }>(
      `/api-tools/${toolId}/test`,
      { arguments: argumentsData }
    );
    return response.data;
  }
};
export interface McpServerItem {
  id: number;
  name: string;
  display_name: string;
  description?: string | null;
  transport_type: string;
  command?: string | null;
  args?: string[] | null;
  env_vars?: Record<string, string> | null;
  url?: string | null;
  headers?: Record<string, string> | null;
  is_enabled: boolean;
  requires_approval: boolean;
  status: string;
  last_error?: string | null;
  discovered_tools?: any[] | null;
  discovered_resources?: { uri: string; name: string; description?: string | null; mimeType?: string | null }[];
  discovered_prompts?: { name: string; description?: string | null; arguments: { name: string; description?: string | null; required: boolean }[] }[];
  oauth_client?: { client_id: string; client_secret: string; scope: string } | null;
  oauth_authorized?: boolean;
  timeout: number;
  created_at: string;
  updated_at: string;
}
export const mcpService = {
  async getPresets(): Promise<{ status: string; presets: any[] }> {
    const response = await api.get<{ status: string; presets: any[] }>('/mcp/presets');
    return response.data;
  },
  async getServers(params?: { is_enabled?: boolean }): Promise<{ status: string; total: number; servers: McpServerItem[] }> {
    const response = await api.get<{ status: string; total: number; servers: McpServerItem[] }>('/mcp/servers', {
      params,
    });
    return response.data;
  },
  async createServer(serverData: any): Promise<{ status: string; message: string; server: McpServerItem }> {
    const response = await api.post<{ status: string; message: string; server: McpServerItem }>(
      '/mcp/servers',
      serverData
    );
    return response.data;
  },
  async updateServer(serverId: number, serverData: any): Promise<{ status: string; message: string; server: McpServerItem }> {
    const response = await api.put<{ status: string; message: string; server: McpServerItem }>(
      `/mcp/servers/${serverId}`,
      serverData
    );
    return response.data;
  },
  async deleteServer(serverId: number): Promise<{ status: string; message: string }> {
    const response = await api.delete<{ status: string; message: string }>(`/mcp/servers/${serverId}`);
    return response.data;
  },
  async discoverServer(serverId: number): Promise<{ status: string; message: string; tools_count: number; tools: any[]; server: McpServerItem }> {
    const response = await api.post<{ status: string; message: string; tools_count: number; tools: any[]; server: McpServerItem }>(
      `/mcp/servers/${serverId}/discover`
    );
    return response.data;
  },
  async toggleServer(serverId: number): Promise<{ status: string; is_enabled: boolean; message: string }> {
    const response = await api.patch<{ status: string; is_enabled: boolean; message: string }>(
      `/mcp/servers/${serverId}/toggle`
    );
    return response.data;
  },
  async testTool(serverId: number, toolName: string, argumentsData: Record<string, any>): Promise<{ status: string; tool_name: string; result: any }> {
    const response = await api.post<{ status: string; tool_name: string; result: any }>(
      `/mcp/servers/${serverId}/tools/${encodeURIComponent(toolName)}/test`,
      { arguments: argumentsData }
    );
    return response.data;
  },
  async startOAuth(serverId: number): Promise<{ status: string; authorization_url: string }> {
    const response = await api.post<{ status: string; authorization_url: string }>(`/mcp/servers/${serverId}/oauth/start`);
    return response.data;
  },
  async revokeOAuth(serverId: number): Promise<{ status: string; message: string; server: McpServerItem }> {
    const response = await api.delete<{ status: string; message: string; server: McpServerItem }>(`/mcp/servers/${serverId}/oauth`);
    return response.data;
  }
};
export interface AgentSkillItem {
  id: number;
  name: string;
  description: string;
  license?: string | null;
  compatibility?: string | null;
  metadata?: Record<string, string> | null;
  allowed_tools?: string | null;
  warnings: string[];
  is_enabled: boolean;
  allow_scripts: boolean;
  allowed_user_ids: number[] | null;
  files_present: boolean;
  created_at: string;
  updated_at: string;
}
export interface AgentSkillDetail extends AgentSkillItem {
  body: string | null;
  load_error?: string;
  resources: string[];
  resources_truncated: boolean;
}
export interface EnabledSkill {
  name: string;
  description: string;
}
export const skillService = {
  async getSkills(): Promise<{ status: string; total: number; skills: AgentSkillItem[] }> {
    const response = await api.get<{ status: string; total: number; skills: AgentSkillItem[] }>('/skills');
    return response.data;
  },
  async getEnabledSkills(): Promise<{ status: string; skills: EnabledSkill[] }> {
    const response = await api.get<{ status: string; skills: EnabledSkill[] }>('/skills/enabled');
    return response.data;
  },
  async getSkill(skillId: number): Promise<{ status: string; skill: AgentSkillDetail }> {
    const response = await api.get<{ status: string; skill: AgentSkillDetail }>(`/skills/${skillId}`);
    return response.data;
  },
  async uploadSkill(file: File, replace: boolean): Promise<{ status: string; message: string; skill: AgentSkillItem }> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<{ status: string; message: string; skill: AgentSkillItem }>('/skills/upload', formData, {
      params: { replace },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  async toggleSkill(skillId: number): Promise<{ status: string; is_enabled: boolean; message: string }> {
    const response = await api.patch<{ status: string; is_enabled: boolean; message: string }>(`/skills/${skillId}/toggle`);
    return response.data;
  },
  async updateSkillSettings(
    skillId: number,
    settings: { allow_scripts?: boolean; allowed_user_ids?: number[] }
  ): Promise<{ status: string; message: string; skill: AgentSkillItem }> {
    const response = await api.patch<{ status: string; message: string; skill: AgentSkillItem }>(`/skills/${skillId}/settings`, settings);
    return response.data;
  },
  async deleteSkill(skillId: number): Promise<{ status: string; message: string }> {
    const response = await api.delete<{ status: string; message: string }>(`/skills/${skillId}`);
    return response.data;
  }
};
export default api;

import { describe, expect, it } from 'vitest';
import {
  EMPTY_MCP_FORM,
  EMPTY_TOOL_FORM,
  defaultRequiresApproval,
  emptyTestArgs,
  mcpFormToPayload,
  mcpServerToForm,
  toolFormToPayload,
  toolToForm,
} from './forms';

const MASK = '••••••••';

describe('custom API tool form', () => {
  it('starts empty for a new tool', () => {
    expect(toolToForm(null)).toBe(EMPTY_TOOL_FORM);
  });

  it('round-trips a stored tool and sends the masked token back unchanged', () => {
    const tool = {
      id: 3,
      name: 'get_weather',
      display_name: '天氣',
      description: '查詢天氣',
      method: 'POST',
      url: 'https://api.example.com/weather',
      auth_type: 'bearer',
      auth_config: { token: MASK },
      requires_approval: true,
      timeout: 20,
      parameters_schema: { type: 'object', properties: { city: { type: 'string' } } },
    };

    expect(toolFormToPayload(toolToForm(tool))).toEqual({
      name: 'get_weather',
      display_name: '天氣',
      description: '查詢天氣',
      method: 'POST',
      url: 'https://api.example.com/weather',
      auth_type: 'bearer',
      auth_config: { token: MASK },
      body_content_type: 'application/json',
      requires_approval: true,
      timeout: 20,
      parameters_schema: tool.parameters_schema,
    });
  });

  it('sends only the fields of the selected auth type', () => {
    const form = {
      ...toolToForm({ ...EMPTY_TOOL_FORM, auth_type: 'api_key', auth_config: { key_name: 'X-Key', key_in: 'query', key_value: MASK } }),
      parameters_json: '{}',
    };
    expect(toolFormToPayload(form).auth_config).toEqual({ key_name: 'X-Key', key_in: 'query', key_value: MASK });
    const oauth = { ...form, auth_type: 'oauth2_client_credentials', auth: { ...form.auth, token_url: 'https://auth/token', client_id: 'c', client_secret: 's' } };
    expect(toolFormToPayload(oauth).auth_config).toEqual({ token_url: 'https://auth/token', client_id: 'c', client_secret: 's', scope: '', client_auth: 'basic' });
    expect(toolFormToPayload({ ...form, auth_type: 'none' }).auth_config).toEqual({});
  });

  it('names the field when its JSON is invalid', () => {
    expect(() => toolFormToPayload({ ...EMPTY_TOOL_FORM, parameters_json: '{' })).toThrow('「參數 JSON Schema 定義」不是有效的 JSON');
  });

  it('requires approval by default only for methods that change state', () => {
    expect(['GET', 'head', 'OPTIONS'].map(defaultRequiresApproval)).toEqual([false, false, false]);
    expect(['POST', 'PUT', 'PATCH', 'DELETE'].map(defaultRequiresApproval)).toEqual([true, true, true, true]);
  });
});

describe('MCP server form', () => {
  it('starts empty and requires approval for a new server', () => {
    expect(mcpServerToForm(null)).toBe(EMPTY_MCP_FORM);
    expect(EMPTY_MCP_FORM.requires_approval).toBe(true);
  });

  it('round-trips a stored server', () => {
    const server = {
      name: 'mcp_time',
      display_name: '時間',
      description: '',
      transport_type: 'stdio',
      command: 'uvx',
      args: ['mcp-server-time'],
      env_vars: { TZ: MASK },
      url: '',
      headers: {},
      requires_approval: false,
      timeout: 45,
    };

    expect(mcpFormToPayload(mcpServerToForm(server))).toEqual(server);
  });

  it('names the field when its JSON is invalid', () => {
    expect(() => mcpFormToPayload({ ...EMPTY_MCP_FORM, env_vars_json: '{"a":' })).toThrow('「環境變數配置」不是有效的 JSON');
  });

  it('sends the OAuth client only for HTTP servers and keeps the masked secret', () => {
    const server = { name: 'remote', display_name: '遠端', transport_type: 'http', url: 'https://mcp.example.com/mcp', oauth_client: { client_id: 'c', client_secret: MASK, scope: 'read' } };
    expect(mcpFormToPayload(mcpServerToForm(server)).oauth_client).toEqual({ client_id: 'c', client_secret: MASK, scope: 'read' });
  });
});

describe('test dialog arguments', () => {
  it('has one empty field per declared parameter', () => {
    expect(emptyTestArgs({ properties: { city: {}, days: {} } })).toEqual({ city: '', days: '' });
    expect(emptyTestArgs(undefined)).toEqual({});
  });
});

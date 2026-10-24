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
      requires_approval: true,
      timeout: 20,
      parameters_schema: tool.parameters_schema,
    });
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
});

describe('test dialog arguments', () => {
  it('has one empty field per declared parameter', () => {
    expect(emptyTestArgs({ properties: { city: {}, days: {} } })).toEqual({ city: '', days: '' });
    expect(emptyTestArgs(undefined)).toEqual({});
  });
});

import { describe, expect, it } from 'vitest';
import {
  allEndpointsSelected,
  countSelected,
  describeVersion,
  endpointBadge,
  endpointParameterCount,
  endpointTarget,
  importPayload,
  parseSpecArgs,
  selectAllEndpoints,
  selectedEndpoints,
  toggleAllEndpoints,
} from './openApiImport';
const endpoints = [
  { name: 'get_rate', method: 'GET', path: '/rates', parameters_schema: { properties: { from: {}, to: {} } } },
  { name: 'create_ticket', method: 'POST', path: '/tickets' },
  { name: 'book_trip', kind: 'workflow', method: 'POST', steps_count: 2, step_targets: ['searchFlights', 'bookFlight'] },
];
describe('parse request', () => {
  it('sends an empty base URL as undefined and a trimmed overlay as a one-item list', () => {
    expect(parseSpecArgs('openapi: 3.2.0', '', '  overlay: 1.0.0  ')).toEqual(['openapi: 3.2.0', undefined, ['overlay: 1.0.0']]);
    expect(parseSpecArgs('https://api.example.com/openapi.json', 'https://api.example.com', '   ')).toEqual([
      'https://api.example.com/openapi.json',
      'https://api.example.com',
      [],
    ]);
  });
  it('names the version with the document version when the backend returns it', () => {
    expect(describeVersion({ version: 'openapi_3.2', spec_version: '3.2.0' })).toBe('OpenAPI 3.2（3.2.0）');
    expect(describeVersion({ version: 'arazzo_1.1' })).toBe('Arazzo 1.1');
    expect(describeVersion({ version: 'unknown_9' })).toBe('unknown_9');
  });
});
describe('endpoint selection', () => {
  it('selects every endpoint after parsing', () => {
    const selected = selectAllEndpoints(endpoints, true);
    expect(selected).toEqual({ get_rate: true, create_ticket: true, book_trip: true });
    expect(countSelected(selected)).toBe(3);
    expect(allEndpointsSelected(selected)).toBe(true);
  });
  it('clears everything when all are selected and selects everything otherwise', () => {
    expect(toggleAllEndpoints(selectAllEndpoints(endpoints, true), endpoints)).toEqual({ get_rate: false, create_ticket: false, book_trip: false });
    expect(toggleAllEndpoints({ get_rate: true, create_ticket: false, book_trip: false }, endpoints)).toEqual({ get_rate: true, create_ticket: true, book_trip: true });
  });
  it('imports the selected endpoints in document order', () => {
    expect(selectedEndpoints(endpoints, { book_trip: true, get_rate: true, create_ticket: false }).map((ep) => ep.name)).toEqual(['get_rate', 'book_trip']);
  });
});
describe('import request', () => {
  it('uses the global token as a bearer credential', () => {
    expect(importPayload({ tools: [endpoints[0]], parseResult: { base_url: 'https://api.example.com' }, defaultBaseUrl: '', globalAuthToken: 'secret' })).toEqual({
      tools: [endpoints[0]],
      global_base_url: 'https://api.example.com',
      global_auth_type: 'bearer',
      global_auth_config: { token: 'secret' },
    });
  });
  it('falls back to the typed base URL and sends no credential without a token', () => {
    expect(importPayload({ tools: [], parseResult: { base_url: '' }, defaultBaseUrl: 'https://override.example.com', globalAuthToken: '' })).toEqual({
      tools: [],
      global_base_url: 'https://override.example.com',
      global_auth_type: 'none',
      global_auth_config: {},
    });
  });
});
describe('endpoint rows', () => {
  it('shows a workflow by its steps and an operation by its path', () => {
    expect(endpointBadge(endpoints[2])).toBe('工作流程');
    expect(endpointTarget(endpoints[2])).toBe('2 個步驟：searchFlights、bookFlight');
    expect(endpointTarget({ kind: 'workflow', steps_count: 1 })).toBe('1 個步驟');
    expect(endpointBadge(endpoints[0])).toBe('GET');
    expect(endpointTarget(endpoints[0])).toBe('/rates');
  });
  it('counts declared parameters', () => {
    expect(endpointParameterCount(endpoints[0])).toBe(2);
    expect(endpointParameterCount(endpoints[1])).toBe(0);
  });
});
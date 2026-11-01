import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { describeCustomTool } from './catalog';
import CustomToolRow from './CustomToolRow';
import McpServerRow from './McpServerRow';
import SkillRow from './SkillRow';

const noop = () => {};
const textOf = (html) => html.replace(/<[^>]+>/g, '');
const buttonNamed = (html, text) => [...html.matchAll(/<button([^>]*)>(.*?)<\/button>/gs)]
  .map(([, attrs, inner]) => ({ attrs, text: textOf(inner) }))
  .find((button) => button.text.startsWith(text));
const attribute = (attrs, name) => attrs.match(new RegExp(`\\s${name}="([^"]*)"`))?.[1];
const switchInput = (html) => html.match(/<input[^>]*role="switch"[^>]*>/)[0];

describe('custom tool row', () => {
  const tool = describeCustomTool({
    id: 5,
    name: 'send_ticket',
    display_name: '派遣工單',
    description: '發送工單',
    method: 'POST',
    url: 'https://tickets.example.com/dispatch',
    is_enabled: false,
    requires_approval: true,
    credentials_unreadable: true,
  });
  const html = renderToStaticMarkup(
    <ul>
      <CustomToolRow tool={tool} expanded={false} onToggleDetails={noop} onToggle={noop} onTest={noop} onEdit={noop} onDelete={noop} />
    </ul>
  );

  it('labels the row by its heading and names its switch', () => {
    expect(html).toContain('<article aria-labelledby="tool-custom_5">');
    expect(html).toMatch(/<h3[^>]*id="tool-custom_5"[^>]*>派遣工單<\/h3>/);
    const toggle = switchInput(html);
    expect(attribute(toggle, 'aria-label')).toBe('啟用工具「派遣工單」');
    expect(toggle).not.toMatch(/\schecked=""/);
    expect(textOf(html)).toContain('已停用');
  });

  it('shows the approval setting and the credentials notice', () => {
    expect(textOf(html)).toContain('呼叫前需確認');
    expect(textOf(html)).toContain('憑證需要重新輸入');
  });

  it('keeps details collapsed and out of the tab order until expanded', () => {
    const toggle = buttonNamed(html, '詳細資訊');
    expect(attribute(toggle.attrs, 'aria-expanded')).toBe('false');
    const regionId = attribute(toggle.attrs, 'aria-controls');
    const region = html.slice(html.indexOf(`id="${regionId}"`));
    expect(region.slice(0, region.indexOf('>', region.indexOf('<div', 1)) + 1)).toContain('inert=""');
  });

  it('gives repeated actions a unique accessible name', () => {
    expect(buttonNamed(html, '編輯配置').text).toBe('編輯配置「派遣工單」');
    expect(buttonNamed(html, '刪除工具').text).toBe('刪除工具「派遣工單」');
  });
});

describe('MCP server row', () => {
  const server = {
    id: 9,
    name: 'mcp_docs',
    display_name: '文件搜尋',
    transport_type: 'http',
    url: 'https://mcp.example.com/mcp',
    is_enabled: true,
    status: 'error',
    last_error: '連線逾時',
    oauth_authorized: true,
    discovered_tools: [{ name: 'search_docs', description: '搜尋文件' }],
  };
  const html = renderToStaticMarkup(
    <ul>
      <McpServerRow
        server={server}
        expanded
        discovering={false}
        onToggleDetails={noop}
        onToggle={noop}
        onDiscover={noop}
        onEdit={noop}
        onStartOAuth={noop}
        onRevokeOAuth={noop}
        onTestTool={noop}
        onDelete={noop}
      />
    </ul>
  );

  it('shows the connection error and the OAuth actions of an HTTP server', () => {
    expect(textOf(html)).toContain('連線錯誤');
    expect(textOf(html)).toContain('連線逾時');
    expect(buttonNamed(html, '重新 OAuth 授權')).toBeDefined();
    expect(buttonNamed(html, '清除授權')).toBeDefined();
  });

  it('lists the discovered tools with a test action when expanded', () => {
    expect(attribute(buttonNamed(html, '提供的工具（1）').attrs, 'aria-expanded')).toBe('true');
    expect(buttonNamed(html, '線上測試').text).toBe('線上測試 search_docs');
  });
});

describe('skill row', () => {
  const skill = {
    id: 4,
    name: 'pdf-forms',
    description: '填寫 PDF 表單',
    is_enabled: true,
    files_present: false,
    allowed_user_ids: [1, 2],
    allow_scripts: true,
    warnings: ['缺少 license'],
  };
  const html = renderToStaticMarkup(
    <ul>
      <SkillRow
        skill={skill}
        expanded={false}
        onToggleDetails={noop}
        onToggle={noop}
        onToggleScripts={noop}
        onView={noop}
        onUpload={noop}
        onAccess={noop}
        onUseInChat={noop}
        onDelete={noop}
      />
    </ul>
  );

  it('cannot be used in chat while its files are missing', () => {
    expect(textOf(html)).toContain('找不到技能檔案');
    expect(buttonNamed(html, '在對話中使用').attrs).toMatch(/\sdisabled=""/);
  });

  it('summarises access, scripts and spec warnings on the row', () => {
    expect(textOf(html)).toContain('限 2 位使用者');
    expect(textOf(html)).toContain('可執行腳本');
    expect(textOf(html)).toContain('1 項規格提醒');
  });
});

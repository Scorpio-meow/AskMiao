import { useState } from 'react';
import { mcpService } from '../../services/api';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { emptyTestArgs } from './forms';
import { getRequestErrorMessage } from './shared';
import { TestArgsFields, TestResult } from './ToolTestParts';
import styles from './AiTools.module.css';
export default function McpToolTestDialog({ server, tool, onClose }) {
  const [args, setArgs] = useState(() => emptyTestArgs(tool.inputSchema));
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const handleRun = async () => {
    try {
      setTesting(true);
      const res = await mcpService.testTool(server.id, tool.name, args);
      setResult(res.result);
    } catch (err) {
      setResult({
        is_success: false,
        error: getRequestErrorMessage(err, 'MCP 工具呼叫失敗')
      });
    } finally {
      setTesting(false);
    }
  };
  return (
    <Dialog open onClose={onClose} maxWidth="lg">
      <DialogTitle onClose={onClose} subtitle={`MCP 伺服器：${server.display_name}`}>
        即時測試 MCP 工具：{tool.name}
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        <div className={styles.requestLine}>
          <span className={styles.transportBadge}>tools/call</span>
          <span className={styles.requestDescription}>{tool.description || '無詳細說明'}</span>
        </div>
        <TestArgsFields
          idPrefix="mcp-arg"
          schema={tool.inputSchema}
          args={args}
          onChange={setArgs}
          emptyText="此 MCP 工具無須輸入額外參數"
        />
        <div aria-live="polite">
          {result && (
            <TestResult
              title="MCP 回傳結果"
              success={result.is_success}
              facts={result.duration_seconds !== undefined ? [`耗時 ${result.duration_seconds}s`] : []}
              body={JSON.stringify(result.content || result, null, 2)}
            />
          )}
        </div>
      </DialogContent>
      <DialogActions>
        <Button variant="secondary" onClick={onClose}>
          關閉
        </Button>
        <Button
          variant="primary"
          onClick={handleRun}
          loading={testing}
          startIcon={<Icon name="send" size={16} />}
        >
          {testing ? '正在呼叫 MCP...' : '發送 MCP 測試請求'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
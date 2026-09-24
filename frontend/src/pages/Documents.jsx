import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import api from '../services/api';
import { useDocuments, getApiErrorMessage } from '../hooks/useDocuments';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import {
  Button,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  ConfirmDialog,
  Spinner,
  Alert,
  Chip,
  Icon
} from '../components/ui';
import styles from './Documents.module.css';
const documentsCache = {
  data: null,
  timestamp: 0
};
const createUploadItem = (file) => ({
  file,
  progress: 0,
  status: 'ready',
  controller: null,
  detail: null
});
function Documents() {
  const {
    documents,
    loading,
    loaded,
    error: fetchError,
    clearError: clearFetchError,
    fetchDocuments,
    deleteDocument
  } = useDocuments();
  const [localError, setLocalError] = useState('');
  const [success, setSuccess] = useState('');
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadItems, setUploadItems] = useState([]);
  const [uploadDialog, setUploadDialog] = useState(false);
  const [uploadFinished, setUploadFinished] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [deletingIds, setDeletingIds] = useState({});
  const [pendingDelete, setPendingDelete] = useState(null);
  const [regeneratingStatus, setRegeneratingStatus] = useState({});
  const [pendingRegenerate, setPendingRegenerate] = useState(null);
  const [editingDocId, setEditingDocId] = useState(null);
  const [editingDesc, setEditingDesc] = useState('');
  const [savingDesc, setSavingDesc] = useState(false);
  const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false);
  const [rebuildLoading, setRebuildLoading] = useState(false);
  const [rebuildDialog, setRebuildDialog] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const isMountedRef = useRef(true);
  const fileInputRef = useRef(null);
  const cancelAllRef = useRef(false);
  useDocumentTitle('知識庫');
  useEffect(() => {
    isMountedRef.current = true;
    fetchDocuments();
    return () => {
      isMountedRef.current = false;
    };
  }, [fetchDocuments]);
  const processFiles = (files) => {
    if (!files || !files.length) return;
    const allowedExtensions = [
      '.txt', '.md', '.markdown', '.pdf', '.docx', '.pptx', '.xlsx',
      '.csv', '.json', '.yaml', '.yml', '.xml', '.html', '.htm', '.log',
      '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.cpp', '.c', '.sql',
      '.sh', '.ini', '.env'
    ];
    const allowedTypes = [
      'text/plain',
      'text/markdown',
      'text/x-markdown',
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'text/csv',
      'application/csv',
      'application/json',
      'text/json',
      'text/html',
      'text/xml',
      'application/xml',
      'text/yaml',
      'application/x-yaml'
    ];
    const maxSize = 50 * 1024 * 1024;
    const accepted = [];
    for (const file of files) {
      const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
      const isAllowed = allowedTypes.includes(file.type) || allowedExtensions.includes(ext) || file.type.startsWith('text/');
      if (!isAllowed) {
        setLocalError(`不支援的檔案類型（${file.name}）。支援 PDF、Word、PPT、Excel、Markdown、CSV、JSON、HTML、程式碼等檔案`);
        return;
      }
      if (file.size > maxSize) {
        setLocalError(`檔案大小不能超過 50MB（${file.name}）`);
        return;
      }
      if (!selectedFiles.some(f => f.name === file.name && f.size === file.size)) {
        accepted.push(file);
      }
    }
    if (!accepted.length) return;
    setSelectedFiles((prev) => [...prev, ...accepted]);
    setUploadItems((prev) => [...prev, ...accepted.map(createUploadItem)]);
    setLocalError('');
  };
  const handleFileSelect = (event) => {
    const files = Array.from(event.target.files || []);
    processFiles(files);
    if (event.target) event.target.value = '';
  };
  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };
  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDragging) setIsDragging(true);
  };
  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragging(false);
    }
  };
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(Array.from(e.dataTransfer.files));
    }
  };
  const getStatusChipProps = (status) => {
    switch (status) {
      case 'uploading':
        return { label: '處理中', color: 'primary', icon: <Spinner size={12} color="currentColor" aria-hidden="true" /> };
      case 'success':
        return { label: '已入庫', color: 'success', icon: <Icon name="check" size={12} /> };
      case 'failed':
        return { label: '失敗', color: 'error', icon: <Icon name="error" size={12} /> };
      case 'duplicate':
        return { label: '已存在', color: 'warning', icon: <Icon name="warning" size={12} /> };
      case 'canceled':
        return { label: '已取消', color: 'default' };
      case 'ready':
      default:
        return { label: '待上傳', color: 'default', variant: 'outlined' };
    }
  };
  const getFileBadgeClass = (ext) => {
    const e = ext.toLowerCase();
    if (e === 'pdf') return styles.fileBadgePdf;
    if (e === 'docx' || e === 'doc') return styles.fileBadgeDocx;
    if (e === 'pptx' || e === 'ppt') return styles.fileBadgePptx;
    if (e === 'xlsx' || e === 'xls' || e === 'csv') return styles.fileBadgeXlsx;
    if (['py', 'js', 'ts', 'tsx', 'jsx', 'json', 'html', 'sql', 'sh', 'css'].includes(e)) return styles.fileBadgeCode;
    return styles.fileBadgeText;
  };
  const uploadSingle = async (item, index) => {
    if (!item) return 'skipped';
    const controller = new AbortController();
    setUploadItems((prev) => {
      const next = prev.slice();
      next[index] = { ...next[index], status: 'uploading', controller, progress: 0, detail: null };
      return next;
    });
    const formData = new FormData();
    formData.append('file', item.file);
    try {
      const response = await api.post('/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        signal: controller.signal,
        onUploadProgress: (e) => {
          if (e.lengthComputable && e.total) {
            const p = Math.round((e.loaded * 100) / e.total);
            setUploadItems((prev) => {
              const next = prev.slice();
              next[index] = { ...next[index], progress: p };
              return next;
            });
          }
        }
      });
      const res = response.data?.results?.[0];
      if (res && res.status === 'success') {
        setUploadItems((prev) => {
          const next = prev.slice();
          next[index] = { ...next[index], status: 'success', progress: 100, detail: null };
          return next;
        });
        return 'success';
      } else {
        setUploadItems((prev) => {
          const next = prev.slice();
          next[index] = { ...next[index], status: 'failed', detail: res?.detail || '上傳失敗' };
          return next;
        });
        return 'failed';
      }
    } catch (err) {
      console.error('Upload error:', err);
      if ((axios.isCancel && axios.isCancel(err)) || err.name === 'CanceledError') {
        setUploadItems((prev) => {
          const next = prev.slice();
          next[index] = { ...next[index], status: 'canceled', detail: null };
          return next;
        });
        return 'canceled';
      } else {
        setUploadItems((prev) => {
          const next = prev.slice();
          next[index] = { ...next[index], status: 'failed', detail: getApiErrorMessage(err, '上傳失敗，請稍後再試') };
          return next;
        });
        return 'failed';
      }
    }
  };
  const resetUploadQueue = () => {
    setSelectedFiles([]);
    setUploadItems([]);
    setUploadFinished(false);
  };
  const closeUploadDialog = () => {
    if (uploadLoading) return;
    setUploadDialog(false);
    if (uploadFinished) resetUploadQueue();
  };
  const startUpload = async () => {
    if (!selectedFiles || selectedFiles.length === 0) {
      setLocalError('請選擇檔案');
      return;
    }
    setUploadLoading(true);
    setUploadFinished(false);
    setLocalError('');
    setSuccess('');
    cancelAllRef.current = false;
    const itemsToUpload = uploadItems.slice();
    let successCount = 0;
    let unfinishedCount = 0;
    for (let i = 0; i < itemsToUpload.length; i++) {
      const it = itemsToUpload[i];
      if (!it) continue;
      if (it.status === 'success') continue;
      if (cancelAllRef.current) {
        unfinishedCount += 1;
        continue;
      }
      const result = await uploadSingle(it, i);
      if (result === 'success') successCount += 1;
      else unfinishedCount += 1;
    }
    setUploadLoading(false);
    documentsCache.data = null;
    documentsCache.timestamp = 0;
    fetchDocuments();
    if (unfinishedCount === 0) {
      resetUploadQueue();
      setUploadDialog(false);
      setSuccess(`文件上傳完成：成功 ${successCount} 個`);
      return;
    }
    // 有失敗或取消時保留對話框，讓使用者看到每個檔案的結果與原因，也能重試未完成的檔案
    setUploadFinished(true);
  };
  const cancelAllUploads = () => {
    cancelAllRef.current = true;
    for (const it of uploadItems) {
      if (it && it.controller && it.status === 'uploading') {
        try {
          it.controller.abort();
        } catch (e) {
          console.error('Cancel error', e);
        }
      }
    }
  };
  const cancelUpload = (index) => {
    const it = uploadItems[index];
    if (!it || !it.controller) return;
    it.controller.abort();
  };
  const removeSelectedFiles = () => {
    if (uploadLoading) {
      setLocalError('正在上傳中，請先取消上傳後再移除檔案');
      return;
    }
    setConfirmRemoveOpen(true);
  };
  const confirmRemoveSelectedFiles = () => {
    resetUploadQueue();
    setLocalError('');
    setConfirmRemoveOpen(false);
  };
  const removeFileAt = (index) => {
    const it = uploadItems[index];
    if (it && it.status === 'uploading') {
      setLocalError('該檔案正在上傳，請先取消上傳後再移除');
      return;
    }
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setUploadItems((prev) => prev.filter((_, i) => i !== index));
  };
  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    const { id, filename } = pendingDelete;
    setPendingDelete(null);
    setDeletingIds((prev) => ({ ...prev, [id]: true }));
    setLocalError('');
    setSuccess('');
    try {
      await deleteDocument(id);
      setSuccess(`已刪除「${filename}」`);
    } catch (err) {
      console.error('刪除文件錯誤:', err);
      setLocalError(`刪除「${filename}」失敗：${getApiErrorMessage(err, '請稍後再試')}`);
    } finally {
      setDeletingIds((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  };
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };
  const getFileTypeLabel = (contentType, filename = '') => {
    const ext = filename ? ('.' + (filename.split('.').pop() || '').toLowerCase()) : '';
    if (ext === '.pdf' || contentType === 'application/pdf') return 'PDF';
    if (ext === '.docx' || contentType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return 'DOCX';
    if (ext === '.pptx' || contentType === 'application/vnd.openxmlformats-officedocument.presentationml.presentation') return 'PPTX';
    if (ext === '.xlsx' || contentType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') return 'XLSX';
    if (ext === '.md' || ext === '.markdown' || contentType?.includes('markdown')) return 'MD';
    if (ext === '.csv' || contentType?.includes('csv')) return 'CSV';
    if (ext === '.json' || contentType?.includes('json')) return 'JSON';
    if (ext === '.html' || ext === '.htm' || contentType?.includes('html')) return 'HTML';
    if (['.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.cpp', '.c', '.sql', '.sh'].includes(ext)) return ext.slice(1).toUpperCase();
    if (ext === '.txt' || contentType === 'text/plain') return 'TXT';
    if (ext) return ext.slice(1).toUpperCase();
    return 'TXT';
  };
  const handleRebuildIndex = async () => {
    setRebuildLoading(true);
    setLocalError('');
    setSuccess('');
    try {
      const response = await api.post('/documents/rebuild-index');
      const data = response.data;
      const messageParts = [
        `索引重建成功！`,
        `文件: ${data.document_count || 0}`,
        `向量塊: ${data.chunk_count || 0}`,
        `切塊設定: ${data.chunk_size || '?'}/${data.chunk_overlap || '?'}`
      ];
      if (data.qa_pairs_detected && data.qa_pairs_detected > 0) {
        messageParts.push(`Q&A對: ${data.qa_pairs_detected}`);
      }
      setSuccess(messageParts.join(' | '));
      setRebuildDialog(false);
      fetchDocuments();
    } catch (err) {
      console.error('重建索引錯誤:', err);
      setRebuildDialog(false);
      setLocalError('重建索引失敗：' + getApiErrorMessage(err, '請稍後再試'));
    } finally {
      setRebuildLoading(false);
    }
  };
  const handleRegenerateSummary = async (documentId, filename) => {
    setPendingRegenerate(null);
    try {
      setRegeneratingStatus((prev) => ({ ...prev, [documentId]: true }));
      const response = await api.post(`/documents/${documentId}/regenerate-summary`);
      const newDesc = response.data?.description;
      if (newDesc) {
        setSuccess(`《${filename}》的 AI 大綱已重新生成`);
        fetchDocuments();
      }
    } catch (err) {
      console.error('重新生成大綱錯誤:', err);
      setLocalError(`重新生成大綱失敗：${getApiErrorMessage(err, '請稍後再試')}`);
    } finally {
      setRegeneratingStatus((prev) => ({ ...prev, [documentId]: false }));
    }
  };
  const requestRegenerateSummary = (doc) => {
    // 已有大綱（可能是手動編輯過的）時先確認，避免被直接覆蓋
    if (doc.description) {
      setPendingRegenerate(doc);
    } else {
      handleRegenerateSummary(doc.id, doc.filename);
    }
  };
  const handleSaveSummary = async (documentId) => {
    if (!editingDesc || !editingDesc.trim()) {
      setLocalError('大綱內容不能為空');
      return;
    }
    try {
      setSavingDesc(true);
      await api.put(`/documents/${documentId}/summary`, { description: editingDesc.trim() });
      setSuccess('大綱內容已更新');
      setEditingDocId(null);
      fetchDocuments();
    } catch (err) {
      console.error('儲存大綱錯誤:', err);
      setLocalError(`儲存大綱失敗：${getApiErrorMessage(err, '請稍後再試')}`);
    } finally {
      setSavingDesc(false);
    }
  };
  const failedItems = uploadItems.filter((it) => it.status === 'failed');
  const pendingUploadCount = uploadItems.filter((it) => it.status !== 'success').length;
  // 只有第一次載入時顯示整頁載入；之後重新整理保留目前內容與捲動位置
  if (!loaded) {
    return (
      <div className={styles.loadingState}>
        <Spinner size={36} color="var(--color-primary)" />
      </div>
    );
  }
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>知識庫管理</h1>
          {loading && (
            <span className={styles.refreshing}>
              <Spinner size={16} color="var(--color-primary)" aria-hidden="true" />
              <span>更新中...</span>
            </span>
          )}
        </div>
        <div className={styles.actions}>
          <Button
            variant="outline"
            startIcon={<Icon name="tune" size={16} />}
            onClick={() => setRebuildDialog(true)}
            disabled={rebuildLoading}
          >
            {rebuildLoading ? '重建中...' : '重建索引'}
          </Button>
          <Button
            variant="primary"
            startIcon={<Icon name="upload" size={16} />}
            onClick={() => setUploadDialog(true)}
          >
            上傳文件
          </Button>
        </div>
      </div>
      {fetchError && (
        <Alert
          severity="error"
          style={{ marginBottom: '16px' }}
          onClose={clearFetchError}
          action={
            <Button size="sm" variant="outline" onClick={fetchDocuments}>
              重新載入
            </Button>
          }
        >
          {fetchError}
        </Alert>
      )}
      {localError && (
        <Alert severity="error" style={{ marginBottom: '16px' }} onClose={() => setLocalError('')}>
          {localError}
        </Alert>
      )}
      {success && (
        <Alert severity="success" style={{ marginBottom: '16px' }} onClose={() => setSuccess('')}>
          {success}
        </Alert>
      )}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>
            已上傳的文件 ({documents.length})
          </h2>
        </div>
        {documents.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <Icon name="description" size={64} />
            </div>
            <h3 className={styles.emptyTitle}>還沒有上傳任何文件</h3>
            <p className={styles.emptySubtitle}>開始上傳文件來建立您的知識庫</p>
          </div>
        ) : (
          <ul className={styles.docList} role="list">
            {documents.map((doc) => {
              const isDeleting = Boolean(deletingIds[doc.id]);
              return (
                <li key={doc.id} className={styles.docItem} aria-busy={isDeleting || undefined}>
                  <div className={styles.docMain}>
                    <div className={styles.docTitleRow}>
                      <Icon name="description" size={20} color="var(--color-primary)" />
                      <span className={styles.docFilename}>{doc.filename}</span>
                      <Chip label={getFileTypeLabel(doc.file_type, doc.filename)} size="sm" variant="outlined" />
                      {doc.is_processed ? (
                        <Chip label="已處理" size="sm" color="success" variant="outlined" />
                      ) : (
                        <Chip label="處理中" size="sm" color="warning" variant="outlined" />
                      )}
                    </div>
                    {doc.description && (
                      <div className={styles.docDescriptionBox}>
                        <div className={styles.docDescriptionHeader}>
                          <span className={styles.docDescriptionIcon}>
                            <Icon name="sparkles" size={14} />
                          </span>
                          <span>AI 智能大綱與摘要</span>
                          {editingDocId !== doc.id && (
                            <span className={styles.summaryActions}>
                              <button
                                type="button"
                                className={styles.summaryActionBtn}
                                onClick={() => {
                                  setEditingDocId(doc.id);
                                  setEditingDesc(doc.description || '');
                                }}
                              >
                                編輯<span className="sr-only">「{doc.filename}」的大綱</span>
                              </button>
                            </span>
                          )}
                        </div>
                        {editingDocId === doc.id ? (
                          <div className={styles.summaryEditor}>
                            <textarea
                              value={editingDesc}
                              onChange={(e) => setEditingDesc(e.target.value)}
                              className={styles.summaryEditTextarea}
                              rows={3}
                              aria-label={`編輯「${doc.filename}」的大綱`}
                              autoFocus
                            />
                            <div className={styles.summaryEditorActions}>
                              <Button size="sm" variant="text" onClick={() => setEditingDocId(null)} disabled={savingDesc}>
                                取消
                              </Button>
                              <Button size="sm" variant="primary" onClick={() => handleSaveSummary(doc.id)} loading={savingDesc}>
                                儲存
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <span className={styles.docDescriptionText}>
                            {doc.description}
                          </span>
                        )}
                      </div>
                    )}
                    <div className={styles.docMeta}>
                      <span>上傳時間：{new Date(doc.created_at).toLocaleString('zh-TW')}</span>
                    </div>
                  </div>
                  <div className={styles.docActions}>
                    <IconButton
                      size="sm"
                      onClick={() => requestRegenerateSummary(doc)}
                      disabled={regeneratingStatus[doc.id] || isDeleting}
                      aria-label={`重新生成「${doc.filename}」的 AI 大綱`}
                      title="重新生成 AI 大綱"
                    >
                      {regeneratingStatus[doc.id] ? (
                        <Spinner size={16} color="var(--color-primary)" aria-hidden="true" />
                      ) : (
                        <Icon name="sparkles" size={18} color="var(--color-primary)" />
                      )}
                    </IconButton>
                    <IconButton
                      size="sm"
                      onClick={() => setPendingDelete({ id: doc.id, filename: doc.filename })}
                      disabled={isDeleting}
                      aria-label={`刪除「${doc.filename}」`}
                      title="刪除文件"
                    >
                      {isDeleting ? (
                        <Spinner size={16} color="var(--color-error)" aria-hidden="true" />
                      ) : (
                        <Icon name="delete" size={18} color="var(--color-error)" />
                      )}
                    </IconButton>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {/* 上傳文件 Dialog */}
      <Dialog
        open={uploadDialog}
        onClose={uploadLoading ? undefined : closeUploadDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle
          icon={
            <div className={styles.dialogIconBadge}>
              <Icon name="upload" size={20} />
            </div>
          }
          subtitle="支援將多種格式檔案分塊、向量化並存入 RAG 檢索庫"
          onClose={closeUploadDialog}
          closeDisabled={uploadLoading}
        >
          上傳文件到知識庫
        </DialogTitle>
        <DialogContent>
          <input
            ref={fileInputRef}
            accept=".txt,.md,.markdown,.pdf,.docx,.pptx,.xlsx,.csv,.json,.yaml,.yml,.xml,.html,.htm,.log,.py,.js,.ts,.tsx,.jsx,.java,.cpp,.c,.sql,.sh,.ini,.env"
            className={styles.hiddenFileInput}
            type="file"
            multiple
            onChange={handleFileSelect}
          />
          {/* 拖曳上傳放置區，也可以用鍵盤開啟檔案選擇 */}
          <button
            type="button"
            className={`${styles.dropZone} ${isDragging ? styles.dropZoneActive : ''}`}
            onClick={() => fileInputRef.current?.click()}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            disabled={uploadLoading}
          >
            <span className={styles.dropZoneIconWrap}>
              <Icon name="upload" size={28} />
            </span>
            <span className={styles.dropZoneTitle}>
              {isDragging ? '放開以新增檔案' : '拖曳檔案至此處，或點擊選擇檔案'}
            </span>
            <span className={styles.dropZoneSubtitle}>
              支援多檔案批次選取，單一檔案上限 50MB
            </span>
            <span className={styles.formatTagsWrap}>
              <span className={styles.formatTag}>PDF</span>
              <span className={styles.formatTag}>Word (DOCX)</span>
              <span className={styles.formatTag}>PPT (PPTX)</span>
              <span className={styles.formatTag}>Excel (XLSX/CSV)</span>
              <span className={styles.formatTag}>Markdown</span>
              <span className={styles.formatTag}>JSON</span>
              <span className={styles.formatTag}>HTML</span>
              <span className={styles.formatTag}>Code (.py, .js, .ts...)</span>
            </span>
          </button>
          {uploadFinished && pendingUploadCount > 0 && (
            <Alert severity={failedItems.length > 0 ? 'error' : 'warning'} className={styles.uploadSummary}>
              {failedItems.length > 0
                ? `有 ${failedItems.length} 個檔案沒有成功入庫，原因列在各檔案下方。可以修正後重新上傳。`
                : `已取消 ${pendingUploadCount} 個檔案的上傳，可以再次開始上傳。`}
            </Alert>
          )}
          {/* 已選擇檔案佇列 */}
          {selectedFiles && selectedFiles.length > 0 && (
            <div className={styles.selectedFilesBox}>
              <div className={styles.fileQueueHeader}>
                <div className={styles.fileQueueTitle}>
                  待處理清單 ({selectedFiles.length} 個檔案，共 {formatFileSize(selectedFiles.reduce((acc, f) => acc + f.size, 0))})
                </div>
                <Button
                  variant="text"
                  size="sm"
                  onClick={removeSelectedFiles}
                  disabled={uploadLoading}
                  startIcon={<Icon name="delete" size={14} />}
                >
                  清空清單
                </Button>
              </div>
              <ul className={styles.fileQueueList} role="list">
                {selectedFiles.map((f, idx) => {
                  const item = uploadItems[idx] || { progress: 0, status: 'ready', detail: null };
                  const extLabel = getFileTypeLabel(f.type, f.name);
                  const chipProps = getStatusChipProps(item.status);
                  return (
                    <li key={idx} className={styles.fileCard}>
                      <div className={styles.fileCardTop}>
                        <div className={styles.fileCardLeft}>
                          <span className={`${styles.fileBadge} ${getFileBadgeClass(extLabel)}`}>
                            {extLabel}
                          </span>
                          <div className={styles.fileInfoText}>
                            <div className={styles.fileName} title={f.name}>{f.name}</div>
                            <div className={styles.fileSize}>{formatFileSize(f.size)}</div>
                          </div>
                        </div>
                        <div className={styles.fileCardRight}>
                          <Chip
                            label={chipProps.label}
                            color={chipProps.color}
                            variant={chipProps.variant}
                            icon={chipProps.icon}
                            size="sm"
                          />
                          {item.status === 'uploading' ? (
                            <IconButton
                              size="sm"
                              onClick={() => cancelUpload(idx)}
                              aria-label={`取消上傳 ${f.name}`}
                              title="取消此檔案上傳"
                            >
                              <Icon name="close" size={14} />
                            </IconButton>
                          ) : (
                            <IconButton
                              size="sm"
                              onClick={() => removeFileAt(idx)}
                              disabled={uploadLoading}
                              aria-label={`從清單移除 ${f.name}`}
                              title="從清單移除"
                            >
                              <Icon name="delete" size={14} />
                            </IconButton>
                          )}
                        </div>
                      </div>
                      {item.status === 'failed' && item.detail && (
                        <p className={styles.fileError}>{item.detail}</p>
                      )}
                      {/* 進度條 */}
                      {item.status === 'uploading' && (
                        <div>
                          <div
                            className={styles.progressBar}
                            role="progressbar"
                            aria-valuenow={item.progress}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-label={`${f.name} 上傳進度`}
                          >
                            <div className={styles.progressFill} style={{ width: `${item.progress}%` }} />
                          </div>
                          <div className={styles.progressMeta}>
                            <span>{item.progress < 100 ? '上傳中...' : '正在分塊與建立向量索引...'}</span>
                            <span>{item.progress}%</span>
                          </div>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </DialogContent>
        <DialogActions className={styles.uploadActions}>
          <div>
            {uploadLoading && (
              <Button variant="outline" size="sm" onClick={cancelAllUploads}>
                取消全部上傳
              </Button>
            )}
          </div>
          <div className={styles.uploadActionsRight}>
            <Button
              variant="secondary"
              onClick={closeUploadDialog}
              disabled={uploadLoading}
            >
              關閉
            </Button>
            <Button
              variant="primary"
              startIcon={<Icon name="upload" size={16} />}
              onClick={startUpload}
              disabled={pendingUploadCount === 0 || uploadLoading}
              loading={uploadLoading}
            >
              {uploadLoading
                ? '正在入庫處理中...'
                : uploadFinished
                  ? `重新上傳未完成的檔案 (${pendingUploadCount})`
                  : `開始上傳 (${pendingUploadCount})`}
            </Button>
          </div>
        </DialogActions>
      </Dialog>
      {/* 清除確認 Dialog */}
      <ConfirmDialog
        open={confirmRemoveOpen}
        title="確認清空待上傳清單？"
        description={`此操作將清空目前已選取的 ${selectedFiles.length} 個檔案。已入庫的文件不受影響。`}
        confirmLabel="確定清空"
        destructive
        onConfirm={confirmRemoveSelectedFiles}
        onCancel={() => setConfirmRemoveOpen(false)}
      />
      {/* 刪除文件確認 */}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="刪除這份文件？"
        description={`「${pendingDelete?.filename}」會從知識庫移除，此操作無法復原。`}
        confirmLabel="刪除"
        destructive
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
      {/* 重新生成大綱確認 */}
      <ConfirmDialog
        open={Boolean(pendingRegenerate)}
        title="重新生成 AI 大綱？"
        description={`「${pendingRegenerate?.filename}」目前的大綱（包含手動編輯的內容）會被新的 AI 大綱取代。`}
        confirmLabel="重新生成"
        onConfirm={() => handleRegenerateSummary(pendingRegenerate.id, pendingRegenerate.filename)}
        onCancel={() => setPendingRegenerate(null)}
      />
      {/* 重建索引 Dialog */}
      <Dialog
        open={rebuildDialog}
        onClose={rebuildLoading ? undefined : () => setRebuildDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle
          icon={
            <div className={`${styles.dialogIconBadge} ${styles.dialogIconBadgeWarning}`}>
              <Icon name="tune" size={18} />
            </div>
          }
        >
          確認重建知識庫索引？
        </DialogTitle>
        <DialogContent>
          <p className={styles.rebuildText}>
            此操作會依目前的切塊設定，重新建立所有文件的 FAISS 向量索引與 BM25 關鍵字索引。
          </p>
          <ul className={styles.rebuildNotes}>
            <li>適用於調整切塊參數、索引毀損或檢索結果異常時</li>
            <li>文件越多，重建所需時間越長；完成前請勿關閉此視窗</li>
          </ul>
          {rebuildLoading && (
            <div className={styles.rebuildProgress} role="status">
              <Spinner size={28} color="var(--color-primary)" aria-hidden="true" />
              <p>正在重建向量庫與全文檢索索引，請稍候...</p>
            </div>
          )}
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={() => setRebuildDialog(false)} disabled={rebuildLoading}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={handleRebuildIndex}
            loading={rebuildLoading}
            startIcon={<Icon name="refresh" size={16} />}
          >
            確認重建
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}
export default Documents;

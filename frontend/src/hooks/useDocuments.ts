import { useState, useCallback } from 'react';
import { documentService } from '../services/api';
export interface DocumentInfo {
  id: number;
  filename: string;
  content: string;
  file_type: string;
  uploaded_by?: number;
  created_at: string;
  is_processed: boolean;
  description?: string | null;
}
export const getApiErrorMessage = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
};
export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetchDocuments = useCallback(async (): Promise<DocumentInfo[]> => {
    setLoading(true);
    setError(null);
    try {
      const data = await documentService.getDocuments();
      setDocuments(data);
      return data;
    } catch (err: any) {
      setError(getApiErrorMessage(err, '無法載入文件清單'));
      return [];
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, []);
  const deleteDocument = useCallback(async (documentId: number): Promise<void> => {
    await documentService.deleteDocument(documentId);
    setDocuments(prev => prev.filter(doc => doc.id !== documentId));
  }, []);
  return {
    documents,
    loading,
    loaded,
    error,
    clearError: () => setError(null),
    fetchDocuments,
    deleteDocument,
  };
}
export default useDocuments;
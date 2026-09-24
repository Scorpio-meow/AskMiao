import { useEffect } from 'react';
import { APP_NAME } from '../config/brand';
export function useDocumentTitle(pageTitle: string) {
  useEffect(() => {
    document.title = `${pageTitle} - ${APP_NAME}`;
  }, [pageTitle]);
}
export default useDocumentTitle;

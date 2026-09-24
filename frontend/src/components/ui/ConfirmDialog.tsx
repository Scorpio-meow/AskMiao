import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions } from './Dialog';
import { Button } from './Button';
export interface ConfirmDialogProps {
  open: boolean;
  title: React.ReactNode;
  description?: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  /** 破壞性操作：確認鈕用危險樣式，預設焦點放在「取消」 */
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = '取消',
  destructive = false,
  loading = false,
  onConfirm,
  onCancel,
}) => {
  return (
    <Dialog open={open} onClose={loading ? undefined : onCancel} maxWidth="xs">
      <DialogTitle>{title}</DialogTitle>
      {description && <DialogContent>{description}</DialogContent>}
      <DialogActions>
        <Button variant="secondary" onClick={onCancel} disabled={loading} data-autofocus={destructive || undefined}>
          {cancelLabel}
        </Button>
        <Button
          variant={destructive ? 'danger' : 'primary'}
          onClick={onConfirm}
          loading={loading}
          data-autofocus={destructive ? undefined : true}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

/**
 * 複製文字到剪貼簿。非安全環境（例如透過 http 從區網連線）沒有 Clipboard API，
 * 此時改用隱藏 textarea 搭配 execCommand，並在結束後把焦點還給原本的元素。
 */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // 權限被拒時改用下面的方式
    }
  }
  const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.top = '0';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  let copied: boolean;
  try {
    copied = document.execCommand('copy');
  } catch {
    copied = false;
  }
  document.body.removeChild(textarea);
  previouslyFocused?.focus();
  return copied;
}

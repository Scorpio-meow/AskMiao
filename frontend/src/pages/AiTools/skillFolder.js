const SKIPPED_FOLDER_PARTS = new Set(['.git', '__MACOSX', '.DS_Store']);
export function readFolderSelection(fileList) {
  const entries = Array.from(fileList)
    .map((file) => ({ file, path: file.webkitRelativePath }))
    .filter(({ path }) => !path.split('/').some((part) => SKIPPED_FOLDER_PARTS.has(part)));
  if (entries.length === 0) return null;
  return { name: entries[0].path.split('/')[0], entries };
}

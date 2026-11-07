import { describe, expect, it } from 'vitest';
import { readFolderSelection } from './skillFolder';

const fileAt = (path) => ({ webkitRelativePath: path });

describe('skill folder selection', () => {
  it('keeps relative paths and skips repository and macOS metadata', () => {
    const selection = readFolderSelection([
      fileAt('pdf-processing/SKILL.md'),
      fileAt('pdf-processing/references/REFERENCE.md'),
      fileAt('pdf-processing/.git/HEAD'),
      fileAt('pdf-processing/.DS_Store'),
      fileAt('pdf-processing/__MACOSX/._SKILL.md'),
    ]);
    expect(selection.name).toBe('pdf-processing');
    expect(selection.entries.map((entry) => entry.path)).toEqual([
      'pdf-processing/SKILL.md',
      'pdf-processing/references/REFERENCE.md',
    ]);
  });

  it('returns null when nothing is left to upload', () => {
    expect(readFolderSelection([fileAt('skill/.git/HEAD')])).toBeNull();
    expect(readFolderSelection([])).toBeNull();
  });
});

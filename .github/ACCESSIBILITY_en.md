# Accessibility Statement

[繁體中文](ACCESSIBILITY.md) | [English](ACCESSIBILITY_en.md)

AskMiao aims to let everyone ask questions of a knowledge base, including people who use only a keyboard, use a screen reader, need less motion, or work on a phone. This document describes what is in place, the supported environments, known limitations, and how to report accessibility barriers.

## Goal

The web app aims to meet [WCAG 2.2](https://www.w3.org/TR/WCAG22/) Level AA. It has not been audited by a third party, so it does not claim full conformance.

## What is in place

The following applies to the web app (`frontend/`); the motion item also applies to the intro site (`site/`).

**Keyboard**

- Everything can be done with a keyboard alone, with a clearly visible focus indicator; suggested questions, citations, and the upload drop zone are keyboard operable too.
- Pages behind the sign-in start with a "skip to main content" link.
- Dialogs, the mobile conversation list, and the image viewer use the native `<dialog>` element: Esc closes them, the background is inert while they are open, and focus returns to the button that opened them.
- The account menu supports the arrow keys.

**Screen readers**

- Pages declare `lang="zh-TW"`, and accessible names are always in Traditional Chinese rather than mixed with English.
- Every form field label is bound to its input.
- Screen readers are notified when an answer completes, fails, or is stopped.
- The notices for going offline and coming back online are announced too.

**Visuals and motion**

- Text and status colors meet WCAG AA contrast.
- Light, dark, and follow-system themes are applied before the first paint, so pages do not flash white.
- When the system's reduced-motion setting (`prefers-reduced-motion`) is on, animations and transitions are turned off in the web app and the intro site.

**Mobile and input**

- Buttons and inputs are larger on touch devices; inputs use a 16px font size, so iPhones do not zoom in on focus.
- With input methods such as Zhuyin or Cangjie, pressing Enter to pick a character does not send an unfinished message.

**Answers**

- Markdown images in answers are not loaded automatically and are shown as links instead; external links show the actual host name.

## Supported environments

- **Browsers**: the frontend is built with Vite's default target, covering Chrome and Edge 111, Firefox 114, Safari 16.4, and later versions.
- **Interface language**: Traditional Chinese (Taiwan) only; the documentation is also available in English.
- **Assistive technology**: no tested screen reader and browser combinations have been published yet. Reports from people using NVDA, JAWS, VoiceOver, TalkBack, or other software are welcome.

## Known limitations

- **No automated accessibility checks**: ESLint covers only JS / JSX and does not enable `eslint-plugin-jsx-a11y`, and there is no automated check such as axe, so new problems may appear between releases.
- **Chinese-only interface**: people who do not read Chinese need to rely on browser translation.
- **Answers come from a language model**: heading levels, table structure, and image descriptions in answers depend on the model's output and the source documents, so they cannot be guaranteed to be accessible.

## Reporting accessibility barriers

If something does not work for you, report it with the [accessibility issue template](https://github.com/Scorpio-meow/AskMiao/issues/new?template=accessibility.yml). If you cannot use GitHub, you can also email [yao921024@gmail.com](mailto:yao921024@gmail.com).

If you can, describe:

- The page or feature where the problem happens.
- What you were trying to do, and what actually happened.
- The assistive technology you use and its version (for example a screen reader, magnifier, or voice control), plus your browser and operating system.

The maintainer will reply as soon as possible and schedule confirmed problems for a fix.

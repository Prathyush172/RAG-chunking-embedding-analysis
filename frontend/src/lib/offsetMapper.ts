/**
 * src/lib/offsetMapper.ts
 * Utilities for mapping DOM selections and text coordinates to exact character
 * offsets within the cleaned RFC document.
 */

export interface TextSpan {
  char_start: number;
  char_end: number;
  text: string;
}

/**
 * Calculates character offset of a node and offset within a root container.
 */
export function getNodeCharOffset(root: Node, targetNode: Node, targetOffset: number): number {
  let currentOffset = 0;

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  let currentNode = walker.nextNode();

  while (currentNode) {
    if (currentNode === targetNode) {
      return currentOffset + targetOffset;
    }
    currentOffset += currentNode.textContent?.length || 0;
    currentNode = walker.nextNode();
  }

  return currentOffset;
}

/**
 * Maps the current DOM selection within a container element to exact character
 * offsets in the cleaned document text.
 *
 * @param container The container DOM element enclosing the rendered text
 * @param baseOffset The character offset where the container text starts (e.g. For sliced/virtualized views)
 * @param fullDocText The full cleaned document text for bounds checking and verification
 */
export function getSelectionOffsets(
  container: HTMLElement,
  baseOffset = 0,
  fullDocText?: string
): TextSpan | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
    return null;
  }

  const range = selection.getRangeAt(0);

  // Ensure selection is inside container
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
    return null;
  }

  const startWithinContainer = getNodeCharOffset(container, range.startContainer, range.startOffset);
  const endWithinContainer = getNodeCharOffset(container, range.endContainer, range.endOffset);

  const char_start = baseOffset + Math.min(startWithinContainer, endWithinContainer);
  const char_end = baseOffset + Math.max(startWithinContainer, endWithinContainer);

  const selected_text = fullDocText
    ? fullDocText.slice(char_start, char_end)
    : range.toString();

  return {
    char_start,
    char_end,
    text: selected_text,
  };
}

/**
 * Normalises whitespace in a string while preserving word boundaries.
 */
export function normalizeWhitespace(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/**
 * Locates a quote inside full document text using whitespace-tolerant matching,
 * returning the exact character offsets in the original text.
 */
export function findQuoteInText(fullText: string, quote: string): TextSpan | null {
  const trimmed = quote.trim();
  if (!trimmed) return null;

  // 1. Direct match attempt
  const directIdx = fullText.indexOf(trimmed);
  if (directIdx !== -1) {
    return {
      char_start: directIdx,
      char_end: directIdx + trimmed.length,
      text: fullText.slice(directIdx, directIdx + trimmed.length),
    };
  }

  // 2. Whitespace-flexible regex match
  const words = trimmed.split(/\s+/).filter(Boolean);
  if (words.length === 0) return null;

  const escapedWords = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = escapedWords.join("\\s+");

  try {
    const re = new RegExp(pattern, "m");
    const match = re.exec(fullText);
    if (match) {
      return {
        char_start: match.index,
        char_end: match.index + match[0].length,
        text: match[0],
      };
    }
  } catch {
    // Fall through
  }

  return null;
}

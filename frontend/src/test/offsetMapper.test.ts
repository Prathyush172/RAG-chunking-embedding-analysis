import { describe, it, expect, beforeEach } from "vitest";
import {
  getNodeCharOffset,
  getSelectionOffsets,
  findQuoteInText,
  normalizeWhitespace,
} from "../lib/offsetMapper";

describe("offsetMapper", () => {
  const tcpSnippet = `1.  Introduction

   The Transmission Control Protocol (TCP) is a core protocol of the
   Internet protocol suite.  It originated in the initial network
   implementation in which it complemented the Internet Protocol (IP).`;

  const httpSnippet = `3.  Protocol Parameters

   HTTP uses a "<major>.<minor>" numbering scheme to indicate versions of
   the protocol.  The protocol versioning policy is intended to allow the
   sender to indicate the format of a message and its capacity for
   understanding further HTTP communication.`;

  describe("normalizeWhitespace", () => {
    it("collapses tabs, multiple spaces, and newlines into single spaces", () => {
      const input = "  Hello \t\n world! \n  How   are you?  ";
      expect(normalizeWhitespace(input)).toBe("Hello world! How are you?");
    });
  });

  describe("findQuoteInText", () => {
    it("locates exact single-line substring with precise offsets", () => {
      const quote = "The Transmission Control Protocol (TCP)";
      const match = findQuoteInText(tcpSnippet, quote);
      expect(match).not.toBeNull();
      expect(match?.char_start).toBe(21);
      expect(tcpSnippet.slice(match!.char_start, match!.char_end)).toBe(quote);
    });

    it("locates multi-line quote with normalized whitespace", () => {
      const multiLineQuote =
        "The Transmission Control Protocol (TCP) is a core protocol of the Internet protocol suite.";
      const match = findQuoteInText(tcpSnippet, multiLineQuote);
      expect(match).not.toBeNull();
      expect(match?.char_start).toBe(21);
      const extracted = tcpSnippet.slice(match!.char_start, match!.char_end);
      expect(normalizeWhitespace(extracted)).toBe(multiLineQuote);
    });

    it("locates HTTP protocol parameter quote across line wraps", () => {
      const quote =
        'HTTP uses a "<major>.<minor>" numbering scheme to indicate versions of the protocol.';
      const match = findQuoteInText(httpSnippet, quote);
      expect(match).not.toBeNull();
      const extracted = httpSnippet.slice(match!.char_start, match!.char_end);
      expect(normalizeWhitespace(extracted)).toBe(quote);
    });

    it("returns null for non-existent quote", () => {
      const match = findQuoteInText(tcpSnippet, "Non-existent networking phrase");
      expect(match).toBeNull();
    });
  });

  describe("DOM selection mapping", () => {
    let container: HTMLDivElement;

    beforeEach(() => {
      container = document.createElement("div");
      document.body.appendChild(container);
    });

    it("correctly calculates node character offset across multiple sibling nodes", () => {
      const p1 = document.createElement("p");
      p1.textContent = "First line of text.";
      const p2 = document.createElement("p");
      p2.textContent = "Second line of text.";
      container.appendChild(p1);
      container.appendChild(p2);

      const textNode2 = p2.firstChild!;
      // Target is 7 chars into second line: "Second "
      const offset = getNodeCharOffset(container, textNode2, 7);
      // p1 text length is 19. 19 + 7 = 26.
      expect(offset).toBe(26);
    });

    it("maps window selection within container to document text span", () => {
      const span1 = document.createElement("span");
      span1.textContent = "Transmission Control ";
      const span2 = document.createElement("span");
      span2.textContent = "Protocol (TCP)";
      container.appendChild(span1);
      container.appendChild(span2);

      const range = document.createRange();
      range.setStart(span1.firstChild!, 13); // "Control "
      range.setEnd(span2.firstChild!, 8); // "Protocol"

      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);

      const result = getSelectionOffsets(container, 100);
      expect(result).not.toBeNull();
      expect(result?.char_start).toBe(113); // 100 base + 13
      expect(result?.char_end).toBe(129); // 100 base + 21 + 8 = 129
      expect(result?.text).toBe("Control Protocol");
    });
  });
});

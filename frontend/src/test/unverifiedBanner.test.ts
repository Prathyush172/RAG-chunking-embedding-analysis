import { describe, it, expect } from "vitest";

describe("Unverified Banner Logic", () => {
  function shouldShowUnverifiedBanner(exp: {
    has_unverified?: boolean;
    unverified_questions_count?: number;
    verified_only?: boolean;
  }): boolean {
    if (exp.verified_only) return false;
    if (exp.has_unverified) return true;
    if ((exp.unverified_questions_count ?? 0) > 0) return true;
    return false;
  }

  it("shows banner when has_unverified is true", () => {
    expect(shouldShowUnverifiedBanner({ has_unverified: true, unverified_questions_count: 16 })).toBe(true);
  });

  it("shows banner when unverified_questions_count > 0", () => {
    expect(shouldShowUnverifiedBanner({ unverified_questions_count: 5 })).toBe(true);
  });

  it("hides banner when verified_only is true", () => {
    expect(
      shouldShowUnverifiedBanner({ verified_only: true, has_unverified: true, unverified_questions_count: 16 })
    ).toBe(false);
  });

  it("hides banner when all questions are verified and verified_only is false", () => {
    expect(shouldShowUnverifiedBanner({ has_unverified: false, unverified_questions_count: 0 })).toBe(false);
  });
});

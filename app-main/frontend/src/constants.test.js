import { headerValueLine } from "./constants";

test("header price line uses value_assessment tiers, not the old value_tier words", () => {
  expect(headerValueLine({
    tier: "premium",
    headline: "Priced well above the category average.",
  })).toBe("Priced well above the category average.");
  expect(headerValueLine({
    tier: "underpriced",
    headline: "Priced below category average — good value",
  })).toBeNull();
  expect(headerValueLine({
    tier: "excellent",
    headline: "Well below the typical price for this category.",
  })).toBe("Well below the typical price for this category.");
});

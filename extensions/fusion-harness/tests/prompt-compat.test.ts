import { expect, test } from "bun:test";
import { promptText } from "../modules/runtime.ts";

test("joins OMP system prompt sections for display", () => {
  expect(promptText(["base prompt", "loaded context"])).toBe("base prompt\n\nloaded context");
});

test("preserves Pi string system prompts", () => {
  expect(promptText("base prompt")).toBe("base prompt");
});

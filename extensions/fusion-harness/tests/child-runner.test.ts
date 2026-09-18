import { describe, expect, test } from "bun:test";
import {
  childCatalogueArgs,
  childContextIsolationArgs,
  childExtensionArgsForModels,
  childSessionIdFlag,
  childToolsArg,
  isOmpRuntime,
  parseChildCatalogue,
} from "../modules/child-runner.ts";

describe("clean-room child extensions", () => {
  test("loads the Command Code provider when a stack uses Command Code", () => {
    expect(childExtensionArgsForModels(["commandcode/z-ai/glm-5.3-flash"])).toEqual([
      "--extension",
      "npm:pi-commandcode-provider",
    ]);
  });

  test("does not load provider extensions for native models", () => {
    expect(childExtensionArgsForModels(["openai-codex/gpt-5.6-sol", "google/gemini-3.7-flash"])).toEqual([]);
  });

  test("loads the provider once for mixed stacks", () => {
    expect(
      childExtensionArgsForModels([
        "openai-codex/gpt-5.6-sol",
        "commandcode/z-ai/glm-5.3-flash",
        "commandcode/deepseek/deepseek-v4-flash",
      ]),
    ).toEqual(["--extension", "npm:pi-commandcode-provider"]);
  });

  test("uses OMP's JSON model command and absolute provider entrypoint", () => {
    const args = childCatalogueArgs(["commandcode/z-ai/glm-5.3-flash"], "omp");
    expect(args.slice(0, 2)).toEqual(["--no-extensions", "--extension"]);
    expect(args[2]).toMatch(/[\\/]pi-commandcode-provider[\\/]index\.ts$/);
    expect(args.slice(3)).toEqual(["models", "--json"]);
  });

  test("parses OMP's JSON model catalog", () => {
    expect(
      parseChildCatalogue(
        JSON.stringify({
          models: [
            { provider: "commandcode", id: "z-ai/glm-5.3-flash" },
            { provider: "openai-codex", id: "gpt-5.6-sol" },
          ],
        }),
      ),
    ).toEqual(new Set(["commandcode/z-ai/glm-5.3-flash", "openai-codex/gpt-5.6-sol"]));
  });

  test("does not pass a synthetic session id to OMP", () => {
    expect(childSessionIdFlag("omp")).toBeUndefined();
    expect(childContextIsolationArgs("omp")).toEqual([]);
  });
  test("detects a Bun-compiled OMP launcher", () => {
    expect(isOmpRuntime(["bun", "/$bunfs/root/omp-linux-x64"])).toBe(true);
  });

  test("does not classify a Bun-compiled Pi launcher as OMP", () => {
    expect(isOmpRuntime(["bun", "/$bunfs/root/pi-linux-x64"])).toBe(false);
  });


  test("keeps Pi's session and context isolation flags", () => {
    expect(childSessionIdFlag("pi")).toBe("--session-id");
    expect(childContextIsolationArgs("pi")).toEqual(["--no-context-files"]);
  });
  test("maps Pi-only tool names to OMP's tool catalog", () => {
    expect(childToolsArg("read,grep,find,ls", "omp")).toBe("read,grep,glob");
    expect(childToolsArg("read,grep,find,ls,bash,edit,write", "omp")).toBe("read,grep,glob,bash,edit,write");
  });

  test("keeps Pi tool names unchanged", () => {
    expect(childToolsArg("read,grep,find,ls", "pi")).toBe("read,grep,find,ls");
  });
});
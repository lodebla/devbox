import { afterEach, describe, expect, mock, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Host-provided packages only exist inside a pi/omp process.
mock.module("@earendil-works/pi-tui", () => ({
	Box: class {},
	Container: class {},
	Markdown: class {},
	Text: class {},
	matchesKey: () => false,
	truncateToWidth: (text: string) => text,
	visibleWidth: (text: string) => text.length,
	wrapTextWithAnsi: (text: string) => [text],
}));
mock.module("@earendil-works/pi-coding-agent", () => ({ getMarkdownTheme: () => ({}) }));

const { default: fusionHarness } = await import("../fusion-harness.ts");

const HOST = "openai-codex/gpt-6-luna";
const ARCHITECT = "anthropic/claude-fable-5";
const SOL = "openai-codex/gpt-6-sol";
const dirs: string[] = [];

afterEach(() => {
	delete process.env.FH_CONFIG;
	while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true });
});

function useStack(solIsPrimary: boolean) {
	const dir = mkdtempSync(join(tmpdir(), "fh-host-model-"));
	dirs.push(dir);
	const config = join(dir, "model-stack-trio.yaml");
	writeFileSync(config, `- name: ari\n  model: ${ARCHITECT}\n  architect: true\n- name: sol\n  model: ${SOL}\n${solIsPrimary ? "  primary: true\n" : ""}`);
	process.env.FH_CONFIG = config;
	return dir;
}

type Handler = (event: unknown, ctx: unknown) => Promise<void>;
type Command = { handler: (args: string, ctx: unknown) => Promise<void> };

function harness(cwd: string, kind: "main" | "sub") {
	const handlers: Handler[] = [];
	const commands: Record<string, Command> = {};
	const calls = { setModel: [] as string[], setThinking: [] as string[], catalogueRuns: 0, choices: [] as string[] };
	const pi = new Proxy(
		{},
		{
			get: (_target, key) => {
				if (key === "on") return (event: string, fn: Handler) => event === "session_start" && handlers.push(fn);
				if (key === "registerCommand") return (name: string, command: Command) => (commands[name] = command);
				if (key === "setModel") return async (model: { provider: string; id: string }) => (calls.setModel.push(`${model.provider}/${model.id}`), true);
				if (key === "setThinkingLevel") return (level: string) => calls.setThinking.push(level);
				if (key === "getThinkingLevel") return () => "high";
				if (key === "exec") {
					return async () => {
						calls.catalogueRuns++;
						const models = [HOST, ARCHITECT, SOL].map((id) => ({ provider: id.split("/")[0], id: id.split("/").slice(1).join("/") }));
						return { code: 0, stdout: JSON.stringify({ models }), stderr: "" };
					};
				}
				return () => undefined;
			},
		},
	);
	fusionHarness(pi as never);
	const ctx = {
		agent: { kind },
		cwd,
		model: { provider: "openai-codex", id: "gpt-6-luna" },
		modelRegistry: { find: (provider: string, id: string) => ({ provider, id }), hasConfiguredAuth: () => true },
		ui: {
			notify: () => {},
			select: async (_title: string, choices: string[]) => {
				calls.choices = choices;
				return undefined; // cancel after reading the slot list
			},
		},
	};
	return {
		calls,
		start: async () => {
			for (const handler of handlers) await handler({}, ctx);
		},
		command: (name: string) => commands[name].handler("", ctx),
	};
}

describe("host model ownership", () => {
	test("a YAML primary slot becomes the host model of the main session", async () => {
		const h = harness(useStack(true), "main");
		await h.start();
		expect(h.calls.setModel).toEqual([SOL]);
	});

	test("without a primary slot the main session keeps OMP's model and /fh-* uses the configured slots", async () => {
		const h = harness(useStack(false), "main");
		await h.start();
		expect(h.calls.setModel).toEqual([]);
		expect(h.calls.setThinking).toEqual([]);

		await h.command("fh-model");
		expect(h.calls.choices).toEqual([
			`◆ ARCHITECT | ari | ${ARCHITECT} (med)`,
			`▲ BUILDER | main | ${HOST} (hi)`,
			`▲ BUILDER | sol | ${SOL} (med)`,
		]);
	});

	test("subagent sessions keep the model OMP resolved for them", async () => {
		const h = harness(useStack(true), "sub");
		await h.start();
		expect(h.calls.setModel).toEqual([]);
		expect(h.calls.catalogueRuns).toBe(0);
	});
});

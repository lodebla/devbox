// OMP devbox panel: phone-friendly control of OMP sessions running in tmux.
//
// Collab guests can only prompt the agent; this panel covers what they cannot:
// starting sessions, slash commands and TUI selectors (typed into the session's
// tmux pane exactly like a keyboard), and one-tap Collab links. No LLM involved.
//
// Auth: a random token stored in DEVBOX_PANEL_TOKEN_FILE. `omp-panel login`
// prints a login URL/QR that sets an HttpOnly cookie. Keep Cloudflare Access
// (or another gate) in front when exposing it beyond the LAN: the panel can
// type into shells.
import { timingSafeEqual } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";

const PORT = Number(process.env.DEVBOX_PANEL_PORT ?? 7690);
const HOST = process.env.DEVBOX_PANEL_HOST ?? "0.0.0.0";
const WORKSPACE = process.env.DEVBOX_PANEL_WORKSPACE ?? "/workspace";
const TOKEN_FILE = process.env.DEVBOX_PANEL_TOKEN_FILE ?? "/persist/panel/token";
const COOKIE = "devbox_panel";
const TOKEN = readFileSync(TOKEN_FILE, "utf8").trim();
if (TOKEN.length < 32) throw new Error(`panel token in ${TOKEN_FILE} is too short`);

const NAME_RE = /^[A-Za-z0-9._-]+$/;
const KEYS: Record<string, true> = {
	Up: true,
	Down: true,
	Left: true,
	Right: true,
	Enter: true,
	Escape: true,
	Tab: true,
	BSpace: true,
	"C-c": true,
	PageUp: true,
	PageDown: true,
	Space: true,
};

async function run(cmd: string[], timeoutMs = 45_000): Promise<string> {
	const proc = Bun.spawn(cmd, { stdout: "pipe", stderr: "pipe", timeout: timeoutMs });
	const [out, err, code] = await Promise.all([
		new Response(proc.stdout).text(),
		new Response(proc.stderr).text(),
		proc.exited,
	]);
	if (code !== 0) throw new Error((err || out).trim() || `${cmd[0]} exited ${code}`);
	return out;
}

async function tmuxSessions(): Promise<{ name: string; attached: boolean; created: number }[]> {
	let out = "";
	try {
		out = await run(["tmux", "list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_created}"]);
	} catch {
		return []; // no tmux server yet
	}
	return out
		.split("\n")
		.filter(Boolean)
		.map(line => {
			const [name, attached, created] = line.split("\t");
			return { name, attached: attached !== "0", created: Number(created) * 1000 };
		});
}

async function sessions() {
	const [tmux, hosts] = await Promise.all([
		tmuxSessions(),
		run(["omp-qr", "--json"]).then(out => JSON.parse(out) as Record<string, any>[]),
	]);
	const byTmux = new Map(hosts.filter(h => h.tmux !== "-").map(h => [h.tmux, h]));
	return tmux
		.map(t => {
			const h = byTmux.get(t.name);
			return {
				tmux: t.name,
				attached: t.attached,
				created: t.created,
				collab: h
					? {
							instanceId: h.instanceId,
							title: h.sessionName ?? null,
							cwd: h.cwd,
							model: `${h.model?.provider}/${h.model?.id}`,
							busy: h.busy,
							inputRequired: h.inputRequired,
							access: h.access,
						}
					: null,
			};
		})
		.sort((a, b) => b.created - a.created);
}

// Resolve a user-supplied session name to an existing tmux session; exact match only.
async function existing(name: string): Promise<string> {
	if (!NAME_RE.test(name) || !(await tmuxSessions()).some(s => s.name === name)) {
		throw new HttpError(404, `no tmux session named ${name}`);
	}
	return `=${name}:`;
}

function workspaceDirs(): string[] {
	try {
		return readdirSync(WORKSPACE, { withFileTypes: true })
			.filter(d => d.isDirectory() && !d.name.startsWith("."))
			.map(d => `${WORKSPACE}/${d.name}`)
			.sort();
	} catch {
		return [];
	}
}

class HttpError extends Error {
	constructor(
		readonly status: number,
		message: string,
	) {
		super(message);
	}
}

function tokenOk(candidate: string | undefined | null): boolean {
	if (!candidate) return false;
	const a = Buffer.from(candidate);
	const b = Buffer.from(TOKEN);
	return a.length === b.length && timingSafeEqual(a, b);
}

function cookieToken(req: Request): string | undefined {
	const header = req.headers.get("cookie") ?? "";
	for (const part of header.split(";")) {
		const [k, ...v] = part.trim().split("=");
		if (k === COOKIE) return decodeURIComponent(v.join("="));
	}
}

const json = (data: unknown, status = 200) => Response.json(data, { status });

async function api(req: Request, url: URL): Promise<Response> {
	const parts = url.pathname.split("/").filter(Boolean).slice(1); // drop "api"
	const body = async () => {
		if (!req.headers.get("content-type")?.includes("application/json")) throw new HttpError(415, "JSON body required");
		return (await req.json()) as Record<string, unknown>;
	};

	if (parts[0] === "sessions" && parts.length === 1) {
		if (req.method === "GET") return json({ sessions: await sessions(), dirs: workspaceDirs() });
		if (req.method === "POST") {
			const { name, dir } = await body();
			if (typeof name !== "string" || !NAME_RE.test(name)) throw new HttpError(400, "name: letters, digits, . _ - only");
			const cwd = typeof dir === "string" && dir.trim() ? dir.trim() : WORKSPACE;
			if (!cwd.startsWith("/")) throw new HttpError(400, "dir must be an absolute path");
			await run(["mkdir", "-p", cwd]);
			await run(["omp-session", "start", name, cwd], 60_000);
			let link: string | null = null;
			try {
				link = (await run(["omp-qr", "--url", `omp-${name}`])).trim();
			} catch {
				// Collab not ready yet; the session list will show it once shared.
			}
			return json({ tmux: `omp-${name}`, link });
		}
	}

	if (parts[0] === "sessions" && parts.length === 3) {
		const name = decodeURIComponent(parts[1]);
		const target = await existing(name);
		const action = parts[2];
		if (action === "screen" && req.method === "GET") {
			const text = await run(["tmux", "capture-pane", "-p", "-t", target]);
			const size = (await run(["tmux", "display-message", "-p", "-t", target, "#{pane_width}x#{pane_height}"])).trim();
			return json({ text: text.replace(/\s+$/, ""), size });
		}
		if (action === "link" && req.method === "GET") {
			const args = ["omp-qr", "--url"];
			if (url.searchParams.get("view") === "1") args.push("--view");
			args.push(name);
			return json({ link: (await run(args)).trim() });
		}
		if (action === "send" && req.method === "POST") {
			const { text, enter } = await body();
			if (typeof text !== "string" || !text) throw new HttpError(400, "text required");
			await run(["tmux", "send-keys", "-t", target, "-l", "--", text]);
			if (enter !== false) {
				// Let the TUI settle its autocomplete popup so Enter submits instead of completing.
				await Bun.sleep(250);
				await run(["tmux", "send-keys", "-t", target, "Enter"]);
			}
			return json({ ok: true });
		}
		if (action === "keys" && req.method === "POST") {
			const { keys } = await body();
			if (!Array.isArray(keys) || keys.length === 0 || !keys.every(k => typeof k === "string" && Object.hasOwn(KEYS, k))) {
				throw new HttpError(400, `keys must be from: ${Object.keys(KEYS).join(", ")}`);
			}
			await run(["tmux", "send-keys", "-t", target, ...(keys as string[])]);
			return json({ ok: true });
		}
		if (action === "resize" && req.method === "POST") {
			// Only meaningful while no terminal client is attached (it would resize back).
			const { width } = await body();
			const w = Number(width);
			if (!Number.isInteger(w) || w < 40 || w > 300) throw new HttpError(400, "width must be 40-300");
			await run(["tmux", "resize-window", "-t", target, "-x", String(w)]);
			return json({ ok: true });
		}
		if (action === "stop" && req.method === "POST") {
			await run(["tmux", "kill-session", "-t", target.slice(0, -1)]);
			return json({ ok: true });
		}
	}
	throw new HttpError(404, "not found");
}

const PAGE = readFileSync(new URL("./index.html", import.meta.url), "utf8");

Bun.serve({
	port: PORT,
	hostname: HOST,
	async fetch(req) {
		const url = new URL(req.url);
		if (url.pathname === "/login") {
			if (!tokenOk(url.searchParams.get("t"))) return new Response("invalid token", { status: 403 });
			const secure = req.headers.get("x-forwarded-proto") === "https" || url.protocol === "https:";
			return new Response(null, {
				status: 303,
				headers: {
					location: "/",
					"set-cookie": `${COOKIE}=${encodeURIComponent(TOKEN)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000${secure ? "; Secure" : ""}`,
				},
			});
		}
		if (!tokenOk(cookieToken(req))) {
			return new Response("Not logged in. Run `omp-panel login` on the devbox and open the printed link.", {
				status: 401,
				headers: { "content-type": "text/plain; charset=utf-8" },
			});
		}
		if (url.pathname === "/" || url.pathname === "/index.html") {
			return new Response(PAGE, {
				headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
			});
		}
		if (url.pathname.startsWith("/api/")) {
			try {
				return await api(req, url);
			} catch (err) {
				if (err instanceof HttpError) return json({ error: err.message }, err.status);
				return json({ error: err instanceof Error ? err.message : String(err) }, 500);
			}
		}
		return new Response("not found", { status: 404 });
	},
});
console.log(`omp panel listening on http://${HOST}:${PORT}`);

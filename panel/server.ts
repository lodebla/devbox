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

// Shown instead of the app when the browser has no valid cookie. Login links
// redirect to `/#t=<token>`: the fragment stays in the address bar, so "Open in
// Chrome" from an in-app browser (Google Lens) carries the token to the real
// browser, where this page trades it for a cookie and drops it from the URL.
const LOGIN_PAGE = `<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>OMP devbox · login</title>
<style>body{margin:0;padding:24px;background:#111418;color:#e6e9ee;font:16px/1.5 system-ui,sans-serif}
code{background:#1b2027;padding:2px 6px;border-radius:6px}input,button{width:100%;box-sizing:border-box;margin-top:8px;padding:12px;border-radius:10px;border:1px solid #2c333d;background:#0c0f13;color:inherit;font:inherit}
button{background:#5aa9ff;color:#06121f;font-weight:600;border:0}#msg{color:#ef5d5d}</style></head><body>
<h2>OMP devbox</h2><p id="msg"></p>
<p>Non sei collegato in questo browser. Sul devbox esegui <code>omp-panel login &lt;url&gt;</code> e apri il QR con Google Lens.
Se il link si apre dentro l'app Google, usa il menu <b>Apri in Chrome</b>: il login passa da solo.</p>
<p>Oppure incolla il token (<code>cat /persist/panel/token</code>):</p>
<input id="t" autocomplete="off" autocapitalize="off" placeholder="token"><button id="go">Entra</button>
<script>
async function login(t) {
  const r = await fetch("/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ t: t.trim() }) });
  if (r.ok) location.replace("/"); else document.getElementById("msg").textContent = "Token non valido o scaduto (omp-panel rotate-token?).";
}
const fromHash = new URLSearchParams(location.hash.slice(1)).get("t");
if (fromHash) login(fromHash);
document.getElementById("go").onclick = () => login(document.getElementById("t").value);
</script></body></html>`;

function sessionCookie(req: Request, url: URL): string {
	const secure = req.headers.get("x-forwarded-proto") === "https" || url.protocol === "https:";
	// Lax, not Strict: the login link is opened from another app (Lens), and a Strict
	// cookie is withheld on that cross-site navigation. API writes need a JSON content
	// type, so cross-site forms still cannot drive the panel.
	return `${COOKIE}=${encodeURIComponent(TOKEN)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000${secure ? "; Secure" : ""}`;
}

Bun.serve({
	port: PORT,
	hostname: HOST,
	async fetch(req) {
		const url = new URL(req.url);
		if (url.pathname === "/login") {
			const ua = req.headers.get("user-agent") ?? "?";
			if (req.method === "POST") {
				const body = (await req.json().catch(() => ({}))) as { t?: unknown };
				const ok = typeof body.t === "string" && tokenOk(body.t);
				console.log(`${new Date().toISOString()} login POST ${ok ? "ok" : "rejected"} ua=${ua}`);
				if (!ok) return json({ error: "invalid token" }, 403);
				return new Response(null, { status: 204, headers: { "set-cookie": sessionCookie(req, url) } });
			}
			const t = url.searchParams.get("t");
			const ok = tokenOk(t);
			console.log(`${new Date().toISOString()} login link ${ok ? "ok" : "rejected"} ua=${ua}`);
			if (!ok) return new Response("invalid token", { status: 403 });
			return new Response(null, {
				status: 303,
				headers: { location: `/#t=${encodeURIComponent(TOKEN)}`, "set-cookie": sessionCookie(req, url) },
			});
		}
		if (!tokenOk(cookieToken(req))) {
			if (url.pathname.startsWith("/api/")) return json({ error: "not logged in" }, 401);
			return new Response(LOGIN_PAGE, {
				status: 401,
				headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
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

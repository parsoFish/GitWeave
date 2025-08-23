// Minimal fetch wrapper with cookie jar support for session-based tests
type CookieJar = Record<string, string>;

function parseSetCookieHeader(header: string): { name: string; value: string } | null {
	// Basic parser: takes first segment before ';'
	const first = header.split(';')[0];
	const idx = first.indexOf('=');
	if (idx === -1) return null;
	const name = first.slice(0, idx).trim();
	const value = first.slice(idx + 1).trim();
	return { name, value };
}

export class HttpClient {
	private baseUrl: string;
	private jar: CookieJar = {};

	constructor(baseUrl: string) {
		this.baseUrl = baseUrl.replace(/\/$/, '');
	}

	private buildCookieHeader(): string | undefined {
		const entries = Object.entries(this.jar);
		if (!entries.length) return undefined;
		return entries.map(([k, v]) => `${k}=${v}`).join('; ');
	}

	private updateCookies(res: Response) {
		const setCookies = (res.headers as any).getSetCookie?.() as string[] | undefined;
		// Node fetch may not expose getSetCookie; try raw headers
		const fromHeaders = setCookies || (res.headers as any).raw?.()['set-cookie'] || [];
		for (const c of fromHeaders as string[]) {
			const parsed = parseSetCookieHeader(c);
			if (parsed) this.jar[parsed.name] = parsed.value;
		}
	}

	async request(path: string, init: RequestInit = {}) {
		const headers = new Headers(init.headers as HeadersInit);
		const cookie = this.buildCookieHeader();
		if (cookie) headers.set('cookie', cookie);
		if (!headers.has('content-type') && init.method && init.method !== 'GET') {
			headers.set('content-type', 'application/json');
		}
		const res = await fetch(`${this.baseUrl}${path}`, {
			...init,
			headers
		} as any);
		this.updateCookies(res);
		const text = await res.text();
		let body: any = undefined;
		try { body = text ? JSON.parse(text) : undefined; } catch {
			body = text;
		}
		return { res, body } as { res: Response; body: any };
	}
}

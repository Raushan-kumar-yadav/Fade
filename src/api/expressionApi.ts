/** expressionApi.ts — typed client for expression endpoints */

function _exprPort(): number { return (window as any).__FADE_PORT__ ?? 8000; }
const _exprBase = () => `http://127.0.0.1:${_exprPort()}`;

async function _eGet<T>(path: string): Promise<T> {
  const r = await fetch(`${_exprBase()}${path}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function _ePost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${_exprBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function _eDel(path: string): Promise<void> {
  await fetch(`${_exprBase()}${path}`, { method: 'DELETE' });
}

export interface ExpressionState {
  expression: string;
  hasExpression: boolean;
  error: string;
}

export const expressionApi = {
  get: (clipId: string, param: string): Promise<ExpressionState> =>
    _eGet(`/clips/${clipId}/expression/${param}`),

  set: (clipId: string, param: string, expression: string) =>
    _ePost(`/clips/${clipId}/expression/${param}`, { expression }),

  clear: (clipId: string, param: string) =>
    _eDel(`/clips/${clipId}/expression/${param}`),

  test: (clipId: string, param: string, expression: string, frame: number) =>
    _ePost<{ ok: boolean; value: number | null; error: string }>(
      `/clips/${clipId}/expression/${param}/test`,
      { expression, frame }
    ),
};

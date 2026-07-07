// Shared SSE-over-fetch primitives. The backend streams `text/event-stream`
// bodies ("event: X\ndata: {json}\n\n") from POST endpoints, so we read them
// with fetch + a manual reader instead of EventSource (which is GET-only).

export type SSEHandler = (event: string, data: unknown) => void;

// Parse a fetch Response body as text/event-stream, dispatching each event.
// Chunks without an event/data pair (e.g. ": keepalive" comments) are ignored.
export async function readSSE(resp: Response, onEvent: SSEHandler): Promise<void> {
  if (!resp.body) throw new Error("No response stream");
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const evMatch = chunk.match(/^event: (.+)$/m);
      const dataMatch = chunk.match(/^data: (.+)$/m);
      if (!evMatch || !dataMatch) continue;
      let data: unknown;
      try {
        data = JSON.parse(dataMatch[1]);
      } catch {
        continue;
      }
      onEvent(evMatch[1], data);
    }
  }
}

// POST (optionally multipart) and stream the SSE response, with abort support.
export async function streamPOST(
  url: string,
  body: FormData | null,
  onEvent: SSEHandler,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(url, { method: "POST", body: body ?? undefined, signal });
  if (!resp.ok && !resp.body) throw new Error(`Stream failed (${resp.status})`);
  await readSSE(resp, onEvent);
}

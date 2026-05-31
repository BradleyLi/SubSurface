import type { VoiceMatchResponse } from "../types/voice";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchLatestVoiceMatch(
  useReal = true,
  transcriptPath?: string | null,
): Promise<VoiceMatchResponse> {
  const params = new URLSearchParams({ use_real: String(useReal) });
  if (transcriptPath) {
    params.set("transcript_path", transcriptPath);
  }
  const url = `${API_BASE}/api/voice/match/latest?${params}`;

  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error(
      "Cannot reach voice match API. Start the SubSurface backend on port 8000.",
    );
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      body.trim() || `Voice match failed (${res.status}).`,
    );
  }

  return res.json() as Promise<VoiceMatchResponse>;
}

export function voiceEventsUrl(): string {
  const configured = import.meta.env.VITE_VOICE_EVENTS_URL;
  if (configured) return configured;

  // In dev, use the Vite proxy (/voice-events → voice server SSE)
  if (import.meta.env.DEV) {
    return `${window.location.origin}/voice-events`;
  }

  const port = import.meta.env.VITE_VOICE_CHAT_PORT ?? "8504";
  const host = window.location.hostname || "127.0.0.1";
  const protocol = window.location.protocol || "http:";
  return `${protocol}//${host}:${port}/api/transcript-events`;
}

export function voiceClientUrl(): string {
  const configured = import.meta.env.VITE_VOICE_CLIENT_URL;
  if (configured) return configured;
  const port = import.meta.env.VITE_VOICE_CHAT_PORT ?? "8504";
  const host = window.location.hostname || "127.0.0.1";
  const protocol = window.location.protocol || "http:";
  return `${protocol}//${host}:${port}/client/`;
}

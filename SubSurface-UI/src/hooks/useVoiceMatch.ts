import { useCallback, useEffect, useState } from "react";
import type { Pipe } from "../types/pipe";
import type { VoiceMatchResponse } from "../types/voice";
import { fetchLatestVoiceMatch, voiceEventsUrl } from "../api/voice";

const STORAGE_PREFIX = "citynerve:lastVoiceTranscriptEvent:";

export interface UseVoiceMatchResult {
  voiceMatch: VoiceMatchResponse | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

export function useVoiceMatch(
  pipes: Pipe[],
  useReal = true,
): UseVoiceMatchResult {
  const [voiceMatch, setVoiceMatch] = useState<VoiceMatchResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const result = await fetchLatestVoiceMatch(useReal);
      setVoiceMatch(result);
    } catch {
      setVoiceMatch(null);
    } finally {
      setLoading(false);
    }
  }, [useReal]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const storageKey = `${STORAGE_PREFIX}react-ui`;
    const eventsUrl = voiceEventsUrl();

    let source: EventSource | null = null;
    try {
      source = new EventSource(eventsUrl);
    } catch {
      return;
    }

    source.addEventListener("transcript", (event) => {
      let payload: { mtime_ns?: number; transcript_path?: string } = {};
      try {
        payload = JSON.parse(event.data || "{}") as typeof payload;
      } catch {
        return;
      }

      const eventId = String(
        payload.mtime_ns ?? payload.transcript_path ?? Date.now(),
      );
      try {
        if (window.localStorage.getItem(storageKey) === eventId) return;
        window.localStorage.setItem(storageKey, eventId);
      } catch {
        /* ignore dedupe failures */
      }

      void refresh();
    });

    return () => {
      source?.close();
    };
  }, [refresh]);

  // When voice match resolves to a pipe, ensure it exists in the loaded network
  useEffect(() => {
    if (!voiceMatch?.match?.pipe_id || pipes.length === 0) return;
    const exists = pipes.some((p) => p.pipe_id === voiceMatch.match?.pipe_id);
    if (!exists) {
      /* match may reference a pipe outside current filters — still show alert */
    }
  }, [voiceMatch, pipes]);

  return { voiceMatch, loading, refresh };
}

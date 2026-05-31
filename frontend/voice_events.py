"""Browser-side bridge from voice transcript events to Streamlit reruns."""

from __future__ import annotations

import json
import os

import streamlit.components.v1 as components


def render_voice_transcript_rerun_listener(*, key: str) -> None:
    """Reload the current Streamlit page when the voice server publishes a transcript."""
    port = int(os.getenv("VOICE_CHAT_PORT", "8503"))
    events_url = os.getenv("VOICE_TRANSCRIPT_EVENTS_URL")
    components.html(
        f"""
<script>
(() => {{
  const configuredEventsUrl = {json.dumps(events_url)};
  const voicePort = {json.dumps(port)};
  const pageHost = window.location.hostname || "127.0.0.1";
  const eventsUrl = configuredEventsUrl || `${{window.location.protocol}}//${{pageHost}}:${{voicePort}}/api/transcript-events`;
  const storageKey = "citynerve:lastVoiceTranscriptEvent:" + {json.dumps(key)};
  let fallbackSeen = null;

  try {{
    const source = new EventSource(eventsUrl);
    source.addEventListener("transcript", (event) => {{
      const payload = JSON.parse(event.data || "{{}}");
      const eventId = String(payload.mtime_ns || payload.transcript_path || Date.now());
      try {{
        if (window.localStorage.getItem(storageKey) === eventId) return;
        window.localStorage.setItem(storageKey, eventId);
      }} catch (err) {{
        if (fallbackSeen === eventId) return;
        fallbackSeen = eventId;
      }}
      window.parent.location.reload();
    }});
  }} catch (err) {{
    console.debug("Voice transcript event listener unavailable", err);
  }}
}})();
</script>
""",
        height=0,
    )

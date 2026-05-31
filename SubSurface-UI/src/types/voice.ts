export interface VoicePipeMatch {
  pipe_id: string;
  confidence: number;
  method: string;
  matched_street: string | null;
  matched_neighbourhood: string | null;
  lat: number | null;
  lon: number | null;
}

export interface VoiceTranscriptPayload {
  session_id: string;
  started_at?: string;
  ended_at?: string;
  model?: string;
  incident?: {
    location?: {
      address?: string;
      lat?: number;
      lon?: number;
    };
  };
  transcript?: { role: string; content: string }[];
}

export interface VoiceMatchResponse {
  payload: VoiceTranscriptPayload | null;
  match: VoicePipeMatch | null;
}

export interface VoiceTranscriptEvent {
  type: string;
  session_id?: string;
  transcript_path?: string;
  filename?: string;
  mtime_ns?: number;
}

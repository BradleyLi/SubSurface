import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const voiceTarget =
    env.VITE_VOICE_PROXY_TARGET ||
    `http://127.0.0.1:${env.VITE_VOICE_CHAT_PORT || "8504"}`;

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
        "/health": {
          target: apiTarget,
          changeOrigin: true,
        },
        "/voice-events": {
          target: voiceTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/voice-events/, "/api/transcript-events"),
        },
      },
    },
  };
});

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const projectRoot = "..";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, projectRoot, "");
  const proxyHttpPort = env.PROXY_HTTP_PORT || "8080";

  return {
    plugins: [react()],
    envDir: projectRoot,
    server: {
      port: 5173,
      proxy: {
        "/api": `http://localhost:${proxyHttpPort}`
      }
    }
  };
});

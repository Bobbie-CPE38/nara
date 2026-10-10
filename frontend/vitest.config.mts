import { defineConfig } from "vitest/config";

export default defineConfig({
  // Resolves the "@/..." imports from tsconfig.json.
  resolve: { tsconfigPaths: true },
  test: {
    include: ["tests/**/*.test.{ts,tsx}"],
    environment: "node",
    clearMocks: true,
  },
});

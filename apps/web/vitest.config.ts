import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    typecheck: {
      tsconfig: "./tsconfig.test.json",
    },
  },
});

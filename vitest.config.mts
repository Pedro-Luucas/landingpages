import { defineConfig } from "vitest/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    {
      name: "stub-css-in-tests",
      enforce: "pre",
      load(id) {
        const file = id.split("?")[0] ?? id;
        if (file.endsWith(".css")) {
          return "export default {}";
        }
      },
    },
  ],
  test: {
    environment: "node",
    include: ["tests/unit/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": root,
      "next/font/google": path.resolve(root, "tests/mocks/next-font-google.ts"),
      "next/image": path.resolve(root, "tests/mocks/next-image.ts"),
    },
  },
});

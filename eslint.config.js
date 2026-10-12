import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/dist/**",
      ".local/**",
      ".venv/**",
      "packages/contracts/api.d.ts",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.ts", "**/*.tsx"],
    languageOptions: {
      globals: {
        fetch: "readonly",
        AbortSignal: "readonly",
        Response: "readonly",
        console: "readonly",
        document: "readonly",
        process: "readonly",
      },
    },
  },
);

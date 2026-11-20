import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
      "next-env.d.ts",
    ],
  },
  {
    rules: {
      // Components must call the API through lib/api (typed client + hooks), never fetch directly.
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Use lib/api/client or lib/api/hooks." },
      ],
    },
  },
  {
    files: [
      "lib/api/http.ts",
      "lib/server/**",
      "app/api/**",
      "e2e/**",
      "**/*.test.ts",
      "**/*.test.tsx",
      "tests/**",
    ],
    rules: { "no-restricted-globals": "off" },
  },
];

export default config;

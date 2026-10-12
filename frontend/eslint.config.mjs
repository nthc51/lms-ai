import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Ranh giới thư mục: phần dùng chung không được phụ thuộc một tính năng cụ thể,
  // và component của khu quản trị chỉ dùng trong khu quản trị. Sửa / bỏ một tính năng không kéo theo phần khác.
  {
    files: ["src/lib/**", "src/components/ui/**", "src/components/app/**", "src/components/content/**"],
    ignores: ["src/**/*.test.ts", "src/**/*.test.tsx"], // test được dựng component thật để kiểm hook
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "@/components/*",
                "!@/components/ui",
                "!@/components/ui/**",
                "!@/components/app",
                "!@/components/app/**",
                "!@/components/content",
                "!@/components/content/**",
              ],
              message: "Phần dùng chung (lib, ui, app, content) không được import component của một tính năng.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/**"],
    // lib / ui / app / content đã bị chặn rộng hơn ở khối trên (khối sau sẽ ghi đè cùng rule nên phải loại ra)
    ignores: [
      "src/components/admin/**",
      "src/app/(main)/admin/**",
      "src/lib/**",
      "src/components/ui/**",
      "src/components/app/**",
      "src/components/content/**",
    ],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/components/admin", "@/components/admin/**"],
              message: "Component khu quản trị chỉ dùng trong khu quản trị. Thứ dùng chung thì chuyển sang components/ui hoặc thư mục của tính năng.",
            },
          ],
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;

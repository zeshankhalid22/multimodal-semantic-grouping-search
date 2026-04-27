/** @type {import('tailwindcss').Config} */
tailwind.config = {
  theme: {
    extend: {
      colors: {
        /* ── Primary (Indigo) ─────────────────────────────────────────── */
        primary: {
          50: "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5" /* DEFAULT — buttons, links, accents          */,
          700: "#4338ca" /* hover state                                */,
          800: "#3730a3" /* pressed / active                           */,
          900: "#312e81",
        },

        /* ── Secondary (Violet) — similarity badges, gradients ────────── */
        secondary: {
          50: "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed" /* DEFAULT                                    */,
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#4c1d95",
        },

        /* ── Surface / Neutral ────────────────────────────────────────── */
        surface: {
          DEFAULT: "#ffffff" /* card background                        */,
          muted: "#f8f9ff" /* table zebra row, subtle fills          */,
          subtle: "#f3f4f6" /* image panel background                 */,
          border: "#e5e7eb" /* card / section borders                 */,
        },

        /* ── Text ────────────────────────────────────────────────────── */
        content: {
          DEFAULT: "#111827" /* headings                              */,
          secondary: "#374151" /* body text                             */,
          muted: "#6b7280" /* captions, labels                      */,
          faint: "#9ca3af" /* placeholders, empty states            */,
          inverse: "#ffffff" /* text on dark/primary backgrounds      */,
        },

        /* ── Semantic ─────────────────────────────────────────────────── */
        success: {
          light: "#d1fae5",
          DEFAULT: "#10b981",
          dark: "#065f46",
        },
        warning: {
          light: "#fef3c7",
          DEFAULT: "#f59e0b",
          dark: "#92400e",
        },
        danger: {
          light: "#fee2e2",
          DEFAULT: "#ef4444",
          dark: "#991b1b",
        },
      },

      /* ── Typography ───────────────────────────────────────────────────── */
      fontFamily: {
        sans: ["Inter", "system-ui", "ui-sans-serif", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
      },

      /* ── Border Radius ────────────────────────────────────────────────── */
      borderRadius: {
        card: "0.75rem" /* 12px — product cards                       */,
        panel: "1rem" /* 16px — detail panels                       */,
        sheet: "1.5rem" /* 24px — modal-like containers               */,
      },

      /* ── Box Shadow ───────────────────────────────────────────────────── */
      boxShadow: {
        card: "0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.06)",
        "card-hover": "0 10px 30px -8px rgb(79 70 229 / 0.22)",
        panel:
          "0 4px 6px -1px rgb(0 0 0 / 0.07), 0 2px 4px -2px rgb(0 0 0 / 0.07)",
      },

      /* ── Transitions ──────────────────────────────────────────────────── */
      transitionDuration: {
        DEFAULT: "150ms",
        fast: "100ms",
        slow: "300ms",
      },
    },
  },
};

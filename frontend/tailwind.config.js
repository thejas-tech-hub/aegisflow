/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', "system-ui", "-apple-system", "sans-serif"],
        display: ['"Space Grotesk"', '"Inter"', "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        command: {
          bg: "#090d16",
          surface: "#111827",
          border: "#1f2937",
        },
      },
    },
  },
  plugins: [],
};

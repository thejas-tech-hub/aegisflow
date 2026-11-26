/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
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

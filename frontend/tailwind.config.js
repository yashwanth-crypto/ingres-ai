/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Groundwater palette: deep water blues against a dry-earth warm grey.
        depth: {
          50: "#eef6f7",
          100: "#d3e7ea",
          600: "#1d6473",
          700: "#164e5b",
          900: "#0b2c34",
        },
      },
      fontFamily: {
        // System stacks only - the demo may run with no internet, so a webfont
        // would silently fall back to something worse.
        sans: ["Segoe UI", "system-ui", "-apple-system", "sans-serif"],
        display: ["Georgia", "Cambria", "Times New Roman", "serif"],
      },
    },
  },
  plugins: [],
};

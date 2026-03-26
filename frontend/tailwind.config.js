/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "hs-bg": "#0e1117",
        "hs-surface": "#141a22",
        "hs-grid": "#2a2d35",
        "hs-text": "#fafafa",
        "hs-grey": "#4a4e69",
        "hs-green": "#00d4aa",
        "hs-red": "#ff4b4b",
        "hs-orange": "#ffa500",
        "hs-teal": "#00d4aa",
      },
    },
  },
  plugins: [],
};

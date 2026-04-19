/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#489c44",
          dark: "#1a3a1a",
          text: "#2d6a2d",
          light: "#edf7ed",
        },
        secondary: {
          DEFAULT: "#fcb44c",
          dark: "#e09830",
          light: "#fff8ec",
        },
        danger: {
          light: "#ffeaea",
          DEFAULT: "#b22222",
          dark: "#8b0000",
          accent: "#cc0000",
        },
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Ubuntu",
          "Cantarell",
          "Noto Sans",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

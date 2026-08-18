/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        status: {
          online: "#16a34a",
          warning: "#ea580c",
          critical: "#dc2626",
          unknown: "#6b7280",
          refreshing: "#2563eb",
        },
      },
    },
  },
  plugins: [],
};

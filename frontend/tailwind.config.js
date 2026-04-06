/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          bg: '#0f172a',
          card: 'rgba(30, 41, 59, 0.7)',
        },
        text: {
          main: '#f8fafc',
          muted: '#94a3b8',
        },
        accent: {
          DEFAULT: '#5C8347',
          glow: 'rgba(92, 131, 71, 0.4)',
        }
      },
      backgroundImage: {
        'glass-gradient': 'linear-gradient(135deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.01))',
      },
      animation: {
        'pulse-slow': 'pulse 12s infinite alternate',
      }
    },
  },
  plugins: [],
}

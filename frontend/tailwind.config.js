/** Monochrome (white on black) theme. Existing slate/indigo classes are remapped here so every view restyles at once. */
const neutral = {
  100: '#fafafa', 200: '#e5e5e5', 300: '#d4d4d4', 400: '#a3a3a3', 500: '#737373',
  600: '#525252', 700: '#404040', 800: '#262626', 900: '#111111', 950: '#000000',
}
/** "indigo" is the primary accent: white on black. */
const ink = {
  50: '#ffffff', 100: '#fafafa', 200: '#e5e5e5', 300: '#d4d4d4', 400: '#d4d4d4',
  500: '#e5e5e5', 600: '#ffffff', 700: '#ffffff', 900: '#262626', 950: '#171717',
}
/** Status colours stay (risk must be legible) but are tuned for black backgrounds. */
const status = (light, mid, btn, deep) => ({
  200: light, 300: light, 400: light, 500: mid, 600: btn, 700: btn, 900: deep, 950: deep,
})
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'] },
      colors: {
        slate: neutral,
        indigo: ink,
        emerald: status('#86efac', '#22c55e', '#15803d', '#052e16'),
        rose: status('#fda4af', '#f43f5e', '#be123c', '#2a0a12'),
        amber: status('#fcd34d', '#f59e0b', '#b45309', '#1c1204'),
      },
    },
  },
  plugins: [],
}

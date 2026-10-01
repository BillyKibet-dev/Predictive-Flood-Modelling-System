/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#1F4E79', accent: '#2E75B6' },
        risk: {
          low: '#22c55e',
          moderate: '#eab308',
          high: '#f59e0b',
          extreme: '#ef4444',
        },
      },
    },
  },
  plugins: [],
}

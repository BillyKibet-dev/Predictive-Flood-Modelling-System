/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        brand: {
          DEFAULT: 'var(--brand)',
          light: 'var(--brand-light)',
        },
        accent: 'var(--accent)',
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        border: 'var(--border)',
        ink: 'var(--text)',
        muted: 'var(--text-muted)',
        risk: {
          low: 'var(--risk-low)',
          mod: 'var(--risk-mod)',
          high: 'var(--risk-high)',
          extreme: 'var(--risk-extreme)',
        },
      },
      borderRadius: {
        card: '8px',
        btn: '6px',
        badge: '4px',
      },
      boxShadow: {
        'card-rest': '0 1px 3px rgba(0,0,0,0.08)',
        'card-hover': '0 4px 16px rgba(0,0,0,0.12)',
        modal: '0 24px 48px rgba(0,0,0,0.20)',
      },
      spacing: {
        18: '72px',
      },
      maxWidth: {
        content: '1280px',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: 0, transform: 'translateY(10px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 200ms ease-out',
      },
    },
  },
  plugins: [],
}

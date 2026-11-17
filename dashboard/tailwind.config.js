/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        brand: {
          DEFAULT: 'var(--brand)',
          light: 'var(--brand-light)',
        },
        accent: 'var(--accent)',
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
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
        card: '12px',
        btn: '8px',
        badge: '4px',
      },
      boxShadow: {
        'card-rest': '0 1px 2px rgba(15,23,42,0.05)',
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

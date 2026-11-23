/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#000000',
        panel: '#101D2C',
        card: '#26364A',
        surface: '#1E293B',
        'surface-2': '#2D3748',
        'text-main': '#FFFFFF',
        'text-muted': '#A0AEC0',
        'border-default': '#333333',
        'accent-amber': '#E9A23B',
        'accent-green': '#16A085',
        'accent-red': '#D64545',
      },
    },
  },
  plugins: [],
}

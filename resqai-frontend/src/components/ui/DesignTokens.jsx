export const DesignTokens = {
  /* Typography Scale */
  fontSizes: {
    h1: '2.25rem',  // 36px
    h2: '1.875rem', // 30px
    'h2-sm': '1.5rem',  // 24px
    body: '1rem',     // 16px
    sm: '0.875rem',   // 14px
    xs: '0.75rem',    // 12px
  },

  fontWeights: {
    regular: 400,
    medium: 500,
    bold: 700,
  },

  /* Spacing Scale (8px base) */
  spacing: {
    0: '0',
    1: '0.25rem',   // 4px
    2: '0.5rem',    // 8px
    2.5: '0.625rem',// 10px
    3: '1rem',      // 16px
    3.5: '1.25rem', // 20px
    4: '1.5rem',    // 24px
    5: '2rem',      // 32px
    6: '2.5rem',    // 40px
    7: '3rem',      // 48px
    8: '3.5rem',    // 56px
    9: '4rem',      // 64px
  },

  /* Radius Scale */
  radius: {
    sm: '0.25rem',  // 4px
    base: '0.5rem', // 8px
    md: '0.75rem',  // 12px
    lg: '1rem',     // 16px
    xl: '1.25rem',  // 20px
    '2xl': '1.5rem',  // 24px
    '3xl': '2rem',    // 32px,
  },

  /* Color Palette */
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
    'border-sm': '1px',
    'border-base': '1px',
    'border-md': '2px',
    'border-lg': '3px',
  },

  /* Shadow Scale */
  shadows: {
    sm: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -1px rgba(0, 0, 0, 0.05)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
  },

  /* Animation Principles */
  animation: {
    default: {
      duration: '0.3s',
      easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
    },
    spring: {
      type: 'spring',
      damping: 1.0,
      stiffness: 250,
      transition: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
    },
  },

  /* Gesture Principles */
  gestures: {
    tap: {
      highlight: 'instant',
      duration: '100ms',
    },
    drag: {
      tracking: '1:1',
      hysteresis: '10px',
    },
  },
};
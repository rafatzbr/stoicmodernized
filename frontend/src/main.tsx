import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#f5f5f5',
      contrastText: '#050505',
    },
    secondary: {
      main: '#d71921',
      contrastText: '#f5f5f5',
    },
    background: {
      default: '#000000',
      paper: '#050505',
    },
    text: {
      primary: '#f5f5f5',
      secondary: 'rgba(245,245,245,0.62)',
      disabled: 'rgba(245,245,245,0.36)',
    },
    divider: 'rgba(245,245,245,0.14)',
    success: {
      main: '#5fcf80',
    },
    warning: {
      main: '#ffb020',
    },
    error: {
      main: '#d71921',
    },
  },
  shape: {
    borderRadius: 0,
  },
  typography: {
    fontFamily: 'Space Grotesk, Inter, system-ui, sans-serif',
    h4: {
      fontWeight: 500,
      letterSpacing: '-0.06em',
    },
    h5: {
      fontWeight: 500,
      letterSpacing: '-0.04em',
    },
    h6: {
      fontWeight: 500,
      letterSpacing: '-0.03em',
    },
    overline: {
      fontFamily: 'Space Mono, ui-monospace, monospace',
      fontSize: '0.72rem',
      letterSpacing: '0.16em',
      fontWeight: 400,
    },
    button: {
      fontFamily: 'Space Mono, ui-monospace, monospace',
      fontSize: '0.76rem',
      letterSpacing: '0.08em',
      fontWeight: 400,
    },
    caption: {
      fontFamily: 'Space Mono, ui-monospace, monospace',
      letterSpacing: '0.04em',
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundImage: 'none',
        },
        '::selection': {
          backgroundColor: '#d71921',
          color: '#f5f5f5',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid rgba(245,245,245,0.14)',
          boxShadow: 'none',
        },
      },
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true,
      },
      styleOverrides: {
        root: {
          borderRadius: 999,
          paddingInline: 14,
        },
        containedPrimary: {
          backgroundColor: '#f5f5f5',
          color: '#050505',
        },
        containedSecondary: {
          backgroundColor: '#d71921',
          color: '#f5f5f5',
        },
        outlined: {
          borderColor: 'rgba(245,245,245,0.2)',
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        variant: 'outlined',
        size: 'small',
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          backgroundColor: 'rgba(255,255,255,0.02)',
        },
      },
    },
    MuiSelect: {
      defaultProps: {
        size: 'small',
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          backgroundColor: '#f5f5f5',
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontFamily: 'Space Mono, ui-monospace, monospace',
          letterSpacing: '0.08em',
          fontSize: '0.76rem',
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 16,
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          backgroundColor: '#050505',
          backgroundImage: 'none',
          border: '1px solid rgba(245,245,245,0.14)',
        },
      },
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </StrictMode>,
);

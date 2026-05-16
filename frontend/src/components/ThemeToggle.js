import React, { useState, useEffect } from 'react';

const THEME_KEY = 'niuniu_theme';

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem(THEME_KEY) || 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  return { theme, toggleTheme };
}

export default function ThemeToggle({ theme, onToggle }) {
  return (
    <span
      onClick={onToggle}
      style={{
        cursor: 'pointer',
        fontSize: 20,
        padding: '0 12px',
        userSelect: 'none',
        lineHeight: '64px',
      }}
      title={theme === 'dark' ? '切换到白天模式' : '切换到黑夜模式'}
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </span>
  );
}

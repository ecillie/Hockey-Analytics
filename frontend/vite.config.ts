/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.d.ts', 'src/test/**'],
      reporter: ['text', 'html', 'lcov', 'cobertura'],
      thresholds: {
        statements: 74.04,
        branches: 61.95,
        functions: 65.55,
        lines: 77.35,
      },
    },
  },
})

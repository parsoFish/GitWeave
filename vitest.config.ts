import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: [
      'tests/**/*.spec.ts',
      'tests/**/*.spec.js'
    ],
  testTimeout: 30000,
  hookTimeout: 30000,
  bail: 0,
    globals: true,
    reporters: ['default'],
    isolate: true
  }
});

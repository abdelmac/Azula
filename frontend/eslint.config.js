import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import vue from 'eslint-plugin-vue'

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/essential'],
  { files: ['**/*.vue'], languageOptions: { parserOptions: { parser: tseslint.parser } } },
  { languageOptions: { globals: { console: 'readonly', document: 'readonly', window: 'readonly', sessionStorage: 'readonly', fetch: 'readonly', URL: 'readonly', URLSearchParams: 'readonly', crypto: 'readonly', setTimeout: 'readonly', clearTimeout: 'readonly', AbortController: 'readonly', DOMException: 'readonly', Intl: 'readonly', RequestInit: 'readonly', Headers: 'readonly', process: 'readonly', HTMLElement: 'readonly', HTMLSelectElement: 'readonly', KeyboardEvent: 'readonly', Event: 'readonly' } }, rules: { 'vue/multi-word-component-names': 'off' } },
)

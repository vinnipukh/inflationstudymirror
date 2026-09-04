import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import staticAdapter from '@sveltejs/adapter-static';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// Pure client-side SPA: the Falcon API is a separate process, so the
			// frontend is a static bundle. Set VITE_API_BASE_URL for a remote API.
			adapter: staticAdapter({ fallback: 'index.html' })
		})
	],
	server: {
		// Lets the dashboard run with VITE_API_BASE_URL= (same-origin /api calls)
		// during development against a locally running Falcon API on :8000.
		proxy: {
			'/api': {
				target: 'http://localhost:8000',
				changeOrigin: true
			}
		}
	}
});

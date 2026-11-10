import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
	// Основной backend — локальный Django на 8000. Для второго (агентского)
	// сервера на отдельном порту цель прокси задаётся через VITE_BACKEND_URL.
	const env = loadEnv(mode, '.', '');
	const backendUrl = env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';
	const backendWsUrl = backendUrl.replace(/^http/, 'ws');

	return {
		plugins: [tailwindcss(), sveltekit()],
		allowedHosts: ['.ngrok-free.app', '.ngrok.app'],
		server: {
			proxy: {
				'/api': {
					target: backendUrl,
					changeOrigin: true
				},
				'/media': {
					target: backendUrl,
					changeOrigin: true
				},
				'/static': {
					target: backendUrl,
					changeOrigin: true
				},
				'/ws': {
					target: backendWsUrl,
					ws: true,
					changeOrigin: true
				}
			}
		}
	};
});

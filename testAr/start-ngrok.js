import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Шлях до ngrok
const ngrokPath = 'D:\\GIT\\ngrok.exe';
const port = 4000;

console.log('🚀 Запускаю ngrok для порту', port);
console.log('📱 Очікуйте HTTPS URL...\n');

const ngrok = spawn(ngrokPath, ['http', port.toString()], {
    stdio: 'inherit',
    shell: true
});

ngrok.on('error', (error) => {
    console.error('❌ Помилка запуску ngrok:', error.message);
    console.error('Переконайтеся що ngrok знаходиться за шляхом:', ngrokPath);
    process.exit(1);
});

ngrok.on('close', (code) => {
    console.log(`\n⏹️  ngrok завершено з кодом ${code}`);
});

// Обробка завершення процесу
process.on('SIGINT', () => {
    console.log('\n⏹️  Зупиняю ngrok...');
    ngrok.kill();
    process.exit(0);
});

process.on('SIGTERM', () => {
    ngrok.kill();
    process.exit(0);
});

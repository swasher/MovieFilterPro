import { toast } from "svelte-sonner";

export class ScanLogger {
  // Список строк лога для отображения
  logs = $state<string[]>([]);
  
  // Текущий тип лога
  logType = $state<'scan' | 'debug' | 'error'>('scan');
  
  // Статус подключения сокета
  isConnected = $state(false);
  
  // Статус сканирования
  isScanning = $state(false);
  
  // Текущий task_id
  currentTaskId = $state<string | null>(null);

  private socket: WebSocket | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    // В конструкторе не подключаемся автоматически, чтобы не спамить при импорте
  }

  // Метод для загрузки начальных логов с сервера
  async loadInitialLogs() {
    try {
      const res = await fetch(`/api/kinozal/logs/${this.logType}`);
      if (res.ok) {
        const text = await res.text();
        this.logs = text.split('\n').filter(Boolean).map(line => this.formatLogLine(line));
      } else {
        this.logs = [];
        console.error("Failed to load logs:", res.statusText);
      }
    } catch (err) {
      this.logs = [];
      console.error("Failed to load logs:", err);
    }
  }

  // Подключение к WebSocket
  connect() {
    if (typeof window === 'undefined') return;
    if (this.socket) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    
    try {
      this.socket = new WebSocket(`${protocol}//${host}/ws/log/`);

      this.socket.onopen = () => {
        this.isConnected = true;
        if (this.reconnectTimeout) {
          clearTimeout(this.reconnectTimeout);
          this.reconnectTimeout = null;
        }
      };

      this.socket.onclose = () => {
        this.isConnected = false;
        this.socket = null;
        // Автореконнект через 3 секунды
        this.reconnectTimeout = setTimeout(() => this.connect(), 3000);
      };

      this.socket.onerror = (err) => {
        console.error("WebSocket error:", err);
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'scan_complete') {
            this.isScanning = false;
            this.currentTaskId = null;
            if (data.status === 'success') {
              toast.success(data.message);
            } else {
              toast.error(data.message);
            }
          } else if (data.type === 'log') {
            const content = this.formatLogLine(data.content as string);
            
            // Фильтруем сообщения на стороне клиента в зависимости от выбранного logType
            if (this.logType === 'debug' && content.startsWith('DEBUG:')) {
              this.logs.push(content);
            } else if (this.logType === 'scan' && content.startsWith('INFO:')) {
              // Отрезаем "INFO:" для чистоты отображения
              this.logs.push(content.replace(/^INFO:\s*/, ''));
            } else if (this.logType === 'error' && content.startsWith('ERROR:')) {
              this.logs.push(content);
            }
          }
        } catch (e) {
          console.error("Error parsing websocket message:", e);
        }
      };
    } catch (err) {
      console.error("Failed to establish WebSocket connection:", err);
    }
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.close();
      this.socket = null;
    }
    this.isConnected = false;
  }

  // Запуск сканирования
  async startScan() {
    try {
      const res = await fetch('/api/kinozal/scan/start', { method: 'POST' });
      if (res.status === 200 || res.status === 202) {
        const data = await res.json();
        this.currentTaskId = data.task_id;
        this.isScanning = true;
        this.logs = []; // очищаем лог при запуске нового процесса
        toast.success("Сканирование успешно запущено!");
      } else {
        const text = await res.text();
        toast.error(`Не удалось запустить сканирование: ${text || res.statusText}`);
      }
    } catch (err) {
      toast.error(`Ошибка при запуске сканирования: ${err}`);
    }
  }

  // Отмена сканирования
  async cancelScan() {
    if (!this.currentTaskId) return;
    try {
      const res = await fetch(`/api/kinozal/scan/cancel/${this.currentTaskId}`, { method: 'POST' });
      if (res.ok) {
        this.isScanning = false;
        this.currentTaskId = null;
        toast.info("Сканирование отменено пользователем.");
      } else {
        toast.error(`Ошибка отмены: ${res.statusText}`);
      }
    } catch (err) {
      toast.error(`Ошибка при отмене сканирования: ${err}`);
    }
  }

  // Очистка лога на сервере
  async clearLog() {
    try {
      const res = await fetch(`/api/kinozal/logs/${this.logType}`, { method: 'DELETE' });
      if (res.ok) {
        this.logs = [];
        toast.success(`Файл лога ${this.logType} очищен.`);
      } else {
        toast.error(`Не удалось очистить лог: ${res.statusText}`);
      }
    } catch (err) {
      toast.error(`Ошибка при очистке лога: ${err}`);
    }
  }

  // Проверка текущего статуса при монтировании
  async checkStatus() {
    try {
      const res = await fetch('/api/kinozal/scan/status');
      if (res.ok) {
        const data = await res.json();
        this.isScanning = data.is_scanning;
        if (data.is_scanning && data.active_task_ids?.length > 0) {
          this.currentTaskId = data.active_task_ids[0];
        }
      }
    } catch (err) {
      console.error("Failed to check status:", err);
    }
  }

  // Декодирование URL-адресов в логах
  private formatLogLine(line: string): string {
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    return line.replace(urlRegex, (url) => {
      try {
        return decodeURIComponent(url.replace(/\+/g, ' '));
      } catch (e) {
        return url;
      }
    });
  }
}

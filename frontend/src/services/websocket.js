import { io } from 'socket.io-client';
import { apiConfig } from '../config/api';

class StockWebSocket {
  constructor() {
    this.socket = null;
    this._callbacks = {
      l2Update: [],
      alertTriggered: [],
      disconnect: [],
      connect: [],
    };
  }

  connect() {
    if (this.socket?.connected) return;

    const token = localStorage.getItem('niuniu_token');
    this.socket = io(apiConfig.baseURL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 10,
      auth: token ? { token } : {},
    });

    this.socket.on('connect', () => {
      console.log('[WS] 已连接');
      this._callbacks.connect.forEach(cb => cb());
    });

    this.socket.on('disconnect', (reason) => {
      console.log('[WS] 已断开:', reason);
      this._callbacks.disconnect.forEach(cb => cb(reason));
    });

    this.socket.on('l2_update', (data) => {
      this._callbacks.l2Update.forEach(cb => cb(data));
    });

    this.socket.on('alert_rule_triggered', (data) => {
      this._callbacks.alertTriggered.forEach(cb => cb(data));
    });

    this.socket.on('error', (data) => {
      console.error('[WS] 服务端错误:', data.message);
    });
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  subscribe(code) {
    if (this.socket?.connected) {
      this.socket.emit('subscribe', { code });
    }
  }

  unsubscribe() {
    if (this.socket?.connected) {
      this.socket.emit('unsubscribe');
    }
  }

  onL2Update(callback) {
    this._callbacks.l2Update.push(callback);
    return () => {
      this._callbacks.l2Update = this._callbacks.l2Update.filter(cb => cb !== callback);
    };
  }

  onAlertTriggered(callback) {
    this._callbacks.alertTriggered.push(callback);
    return () => {
      this._callbacks.alertTriggered = this._callbacks.alertTriggered.filter(cb => cb !== callback);
    };
  }

  onConnect(callback) {
    this._callbacks.connect.push(callback);
    return () => {
      this._callbacks.connect = this._callbacks.connect.filter(cb => cb !== callback);
    };
  }

  onDisconnect(callback) {
    this._callbacks.disconnect.push(callback);
    return () => {
      this._callbacks.disconnect = this._callbacks.disconnect.filter(cb => cb !== callback);
    };
  }

  isConnected() {
    return this.socket?.connected || false;
  }
}

// 单例
export const stockWS = new StockWebSocket();

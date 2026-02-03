import { useEffect, useRef, useState, useCallback } from 'react';
import { ProgressMessage } from '../types';

interface UseWebSocketOptions {
  onMessage?: (message: ProgressMessage) => void;
  onError?: (error: Event) => void;
  onClose?: () => void;
}

export function useWebSocket(taskId: string | null, options: UseWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<ProgressMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const optionsRef = useRef(options);

  // 更新 options ref，避免 connect 依赖变化
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const connect = useCallback(() => {
    if (!taskId) return;

    // 如果已有连接，先关闭
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/progress/${taskId}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // 处理心跳
        if (data === 'ping') {
          ws.send('pong');
          return;
        }

        // 处理连接确认
        if (data.type === 'connected') {
          console.log('WebSocket connection confirmed');
          return;
        }

        // 处理进度消息
        setLastMessage(data as ProgressMessage);
        optionsRef.current.onMessage?.(data as ProgressMessage);
      } catch (e) {
        // 可能是纯文本消息（如pong）
        if (event.data === 'pong') return;
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      optionsRef.current.onError?.(error);
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.log('WebSocket closed');
      optionsRef.current.onClose?.();
    };

    wsRef.current = ws;
  }, [taskId]); // 只依赖 taskId

  useEffect(() => {
    if (taskId) {
      connect();
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [taskId, connect]);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    }
  }, []);

  return {
    isConnected,
    lastMessage,
    sendMessage,
  };
}

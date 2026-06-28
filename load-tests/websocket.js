import ws from 'k6/ws';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.WS_URL || 'ws://localhost:8000/api/v1/marketdata/ws';
const TOKEN = __ENV.TOKEN || '';

export const options = {
  stages: [
    { duration: '10s', target: 5 },
    { duration: '30s', target: 20 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    ws_connecting: ['p(95)<500'],
    ws_msgs_received: ['rate>0'],
  },
};

export default function () {
  const url = TOKEN ? `${BASE_URL}?access_token=${TOKEN}` : BASE_URL;

  ws.connect(url, (socket) => {
    socket.on('open', () => {
      socket.send(JSON.stringify({
        action: 'subscribe',
        symbols: ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS'],
      }));
    });

    socket.on('message', (data) => {
      const msg = JSON.parse(data);
      check(msg, {
        'received tick': (m) => m.type === 'tick',
        'has symbol': (m) => m.symbol !== undefined,
        'has price': (m) => m.last_price > 0,
      });
    });

    socket.setTimeout(() => {
      socket.close();
    }, 10000);
  });

  sleep(1);
}

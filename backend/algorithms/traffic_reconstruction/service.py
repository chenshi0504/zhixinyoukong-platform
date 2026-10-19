from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


LOCAL_APP_PORT = int(os.environ.get('LOCAL_APP_PORT', '8000'))
TARGET_BASE = f'http://127.0.0.1:{LOCAL_APP_PORT}/api/reconstruction'


class ReconstructionProxyHandler(BaseHTTPRequestHandler):
    def _write_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        try:
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _write_body(self, payload):
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _is_health_request(self):
        path = urllib.parse.urlsplit(self.path).path.rstrip('/') or '/'
        return path in ('/health', '/api/health')

    def _write_health(self):
        self._write_json(200, {
            'success': True,
            'status': 'healthy',
            'service': 'traffic_reconstruction_backend',
            'target_base': TARGET_BASE,
        })

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        if self._is_health_request():
            self._write_health()
            return
        self._forward('GET')

    def do_HEAD(self):
        if self._is_health_request():
            self._write_health()
            return
        self._forward('HEAD')

    def do_POST(self):
        self._forward('POST')

    def do_PUT(self):
        self._forward('PUT')

    def do_DELETE(self):
        self._forward('DELETE')

    def _resolve_target_url(self):
        if self.path.startswith('/api/'):
            suffix = self.path[len('/api'):]
            return f'{TARGET_BASE}{suffix}'
        if self.path.startswith('/'):
            return f'{TARGET_BASE}{self.path}'
        return f'{TARGET_BASE}/{self.path}'

    def _forward(self, method):
        target_url = self._resolve_target_url()
        body = None
        content_length = int(self.headers.get('Content-Length', '0') or '0')
        if content_length > 0:
            body = self.rfile.read(content_length)

        headers = {}
        for key, value in self.headers.items():
            if key.lower() not in ('host', 'content-length', 'connection'):
                headers[key] = value

        request = urllib.request.Request(target_url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = response.read()
                self.send_response(response.getcode())
                for key, value in response.headers.items():
                    if key.lower() in ('transfer-encoding', 'connection', 'server', 'date'):
                        continue
                    self.send_header(key, value)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                if method != 'HEAD':
                    self._write_body(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() in ('transfer-encoding', 'connection', 'server', 'date'):
                    continue
                self.send_header(key, value)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                self._write_body(payload)
        except Exception as exc:
            self._write_json(503, {'success': False, 'message': str(exc)})

    def log_message(self, format, *args):
        pass


def main():
    port = 5001
    server = ThreadingHTTPServer(('localhost', port), ReconstructionProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == '__main__':
    main()

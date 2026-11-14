#!/usr/bin/env python3
import socket
import threading
import sys

# Configuración
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 3333
UPSTREAM_HOST = "solo.ckpool.org"
UPSTREAM_PORT = 3333

def forward(source, destination):
    try:
        while True:
            data = source.recv(4096)
            if not data:
                break
            destination.sendall(data)
    except Exception:
        pass
    finally:
        source.close()
        destination.close()

def handle_client(client_socket):
    try:
        upstream_socket = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=10)
        # Crear hilos para bidireccionalidad
        t1 = threading.Thread(target=forward, args=(client_socket, upstream_socket))
        t2 = threading.Thread(target=forward, args=(upstream_socket, client_socket))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception as e:
        print(f"Error conectando a upstream: {e}")
        client_socket.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(5)
    print(f"🚀 Lite Proxy escuchando en {LISTEN_HOST}:{LISTEN_PORT} -> {UPSTREAM_HOST}:{UPSTREAM_PORT}")
    
    while True:
        client_sock, addr = server.accept()
        print(f"✅ Conexión desde {addr}")
        threading.Thread(target=handle_client, args=(client_sock,)).start()

if __name__ == "__main__":
    main()

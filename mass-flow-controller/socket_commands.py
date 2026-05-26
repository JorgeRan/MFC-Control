"""
Unix socket communication for MFC control.
Allows mfc_setpoint_controller.py to send commands to mfc_status_publisher.py
without opening the serial port twice.
"""

import socket
import json
import os
import time

TCP_HOST = "0.0.0.0"
TCP_PORT = 8765


def _send_command(cmd: dict, timeout: float = 5.0) -> dict:
    """Send a generic command payload to the status publisher socket."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((TCP_HOST, TCP_PORT))

        sock.sendall(json.dumps(cmd).encode() + b'\n')

        response = sock.recv(1024).decode().strip()
        sock.close()

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"success": False, "message": f"Invalid response: {response}"}

    except socket.timeout:
        return {"success": False, "message": "Socket command timed out"}
    except Exception as e:
        return {"success": False, "message": f"Socket error: {e}"}


def send_setpoint_command(mfc_id: int, setpoint: float, timeout: float = 5.0) -> dict:
    """
    Send a setpoint command to the status publisher via Unix socket.
    
    Args:
        mfc_id: MFC device index (0 or 1)
        setpoint: Desired flow setpoint in LN/min
        timeout: Socket timeout in seconds
    
    Returns:
        dict with "success" (bool) and "message" (str)
    """
    cmd = {
        "action": "setpoint",
        "mfc_id": mfc_id,
        "setpoint": setpoint,
    }
    return _send_command(cmd, timeout=timeout)


def send_gas_command(mfc_id: int, gas_cmd: int, timeout: float = 5.0) -> dict:
    """Send a gas selection command to the status publisher via TCP socket."""
    cmd = {
        "action": "gas",
        "mfc_id": mfc_id,
        "gas_cmd": gas_cmd,
    }
    return _send_command(cmd, timeout=timeout)


class SocketServer:
    """Unix socket server for receiving MFC control commands."""
    
    def __init__(self, handler_callback):
        """
        Initialize socket server.
        
        Args:
            handler_callback: Function(mfc_id, setpoint) -> bool. Return True if successful.
        """
        self.handler = handler_callback
        self.socket = None
        self.running = False
    
    def start(self):
        """Start the TCP socket server (non-blocking)."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow quick restart
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((TCP_HOST, TCP_PORT))
        self.socket.listen(5)
        self.socket.setblocking(False)
        self.running = True
        print(f"[SocketServer] Listening on {TCP_HOST}:{TCP_PORT}", flush=True)
    
    def handle_one(self):
        """
        Check for one incoming connection and handle it.
        Non-blocking; returns immediately if no client.
        
        Returns:
            bool: True if a command was processed, False if no client waiting
        """
        if not self.running:
            return False
        
        try:
            conn, _ = self.socket.accept()
            conn.settimeout(2.0)

            data = b''
            while True:
                try:
                    chunk = conn.recv(1024)
                except socket.timeout:
                    break
                if not chunk:
                    break
                data += chunk

            lines = data.decode().strip().split('\n')
            for line in lines:
                if not line.strip():
                    continue

                try:
                    cmd = json.loads(line)

                    action = cmd.get("action")
                    if action == "setpoint":
                        mfc_id = cmd.get("mfc_id")
                        setpoint = cmd.get("setpoint")
                        success = self.handler(action, mfc_id, setpoint)
                    elif action == "gas":
                        mfc_id = cmd.get("mfc_id")
                        gas_cmd = cmd.get("gas_cmd")
                        success = self.handler(action, mfc_id, None, gas_cmd)
                    elif action == "refresh":
                        success = self.handler(action)
                    elif action == "status":
                        success = self.handler(action)
                    else:
                        success = False

                    if isinstance(success, dict):
                        response = success
                    else:
                        response = {
                            "success": success,
                            "message": "OK" if success else "Failed"
                        }
                    conn.sendall(json.dumps(response).encode() + b'\n')
                except json.JSONDecodeError as e:
                    response = {"success": False, "message": f"JSON parse error: {e}"}
                    conn.sendall(json.dumps(response).encode() + b'\n')

            conn.close()
            return True

        except BlockingIOError:
            # No client waiting (non-blocking socket)
            return False
        except Exception as e:
            print(f"[SocketServer] Error handling client: {e}", flush=True)
            return False
    
    def stop(self):
        """Stop the socket server and clean up."""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        try:
            os.unlink(SOCKET_FILE)
        except FileNotFoundError:
            pass
        print(f"[SocketServer] Stopped", flush=True)

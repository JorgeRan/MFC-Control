
// Updated for direct Python API (FastAPI on port 5000)
const API_BASE_URL = (() => {
  const fromEnv = import.meta.env.VITE_API_BASE_URL?.trim();
  if (fromEnv) return fromEnv;

  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "https:" : "http:";
    return `${protocol}//${window.location.hostname}:5000`;
  }

  return "http://localhost:5000";
})();


function deviceIdToMfcId(deviceId) {
  if (deviceId === "dev_01") return 0;
  if (deviceId === "dev_02") return 1;
  return null;
}



export async function sendStartSession(selections) {
  const response = await fetch(`${API_BASE_URL}/start-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selections }),
  });
  if (!response.ok) {
    throw new Error(`Failed to start session: ${response.statusText}`);
  }
  return await response.json();
}

export async function fetchSessionState() {
  const response = await fetch(`${API_BASE_URL}/session/state`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch session state: ${response.statusText}`);
  }

  return await response.json();
}

export async function saveSessionState({ sessionActive, selectedGases }) {
  const response = await fetch(`${API_BASE_URL}/session/state`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionActive, selectedGases }),
  });

  if (!response.ok) {
    throw new Error(`Failed to save session state: ${response.statusText}`);
  }

  return await response.json();
}

export async function saveSelectedGas(deviceId, gas) {
  const response = await fetch(`${API_BASE_URL}/session/state/selected-gas`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deviceId, gas }),
  });

  if (!response.ok) {
    throw new Error(`Failed to save selected gas: ${response.statusText}`);
  }

  return await response.json();
}

export async function fetchNodes() {
  try {
    const response = await fetch(`${API_BASE_URL}/nodes`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch nodes: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error fetching nodes:", error);
    throw error;
  }
}

export async function resetSession({ mfc = null } = {}) {
  try {
    const body = mfc != null ? { mfc } : {};
    const response = await fetch(`${API_BASE_URL}/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Failed to reset session: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error resetting session:", error);
    throw error;
  }
}

export async function refreshData() {
  try {
    console.log(`Refreshing Data`);

    const response = await fetch(`${API_BASE_URL}/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to refresh: ${response.statusText}`);
    }

    console.log(`[refreshData] Success`);
    return await response.json();
  } catch (error) {
    console.error("Error refreshing data:", error);
    throw error;
  }
}

/**
 * Fetch metrics for a specific device
 * @param {string} deviceId - Device ID
 */
export async function fetchDeviceMetrics(deviceId) {
  try {
    const response = await fetch(`${API_BASE_URL}/device/${deviceId}/metrics`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch metrics: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error fetching device metrics:", error);
    throw error;
  }
}

export async function fetchDeviceGases(deviceName) {
  try {
    const response = await fetch(`${API_BASE_URL}/device/${deviceName}/fetch-gas`, {
      method: "GET",
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch Gases: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error fetching device metrics:", error);
    throw error;
  }
}

/**
 * Fetch logs for a specific device
 * @param {string} deviceId - Device ID
 */
export async function fetchDeviceLogs(deviceId) {
  try {
    const response = await fetch(`${API_BASE_URL}/device/${deviceId}/logs`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch logs: ${response.statusText}`);
    }

    const data = await response.json();
    return Array.isArray(data) ? data : Array.isArray(data?.logs) ? data.logs : [];
  } catch (error) {
    console.error("Error fetching device logs:", error);
    throw error;
  }
}

/**
 * Send a command to a device
 * @param {string} deviceId - Device ID (dev_01 or dev_02)
 * @param {string} command - Command: 'on', 'off', or 'toggle'
 */
export async function sendCommand(deviceId, command) {
  try {
    const mfcId = deviceIdToMfcId(deviceId);
    if (mfcId === null) {
      throw new Error("Invalid device ID");
    }
    const endpoint = mfcId === 0 ? "/send-command-0" : "/send-command-1";

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ command }),
    });

    if (!response.ok) {
      throw new Error(`Failed to send command: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Error sending command:", error);
    throw error;
  }
}

/**
 * Set setpoint value for a device
 * @param {string} deviceId - Device ID (dev_01 or dev_02)
 * @param {number} value - Setpoint value in LN/min
 */
export async function setSetpoint(deviceId, value) {
  try {
    const mfcId = deviceIdToMfcId(deviceId);
    if (mfcId === null) {
      throw new Error("Invalid device ID");
    }
    const endpoint = mfcId === 0 ? "/setpoint-0" : "/setpoint-1";

    console.log(
      `[setSetpoint] Device: ${deviceId}, Endpoint: ${endpoint}, Value: ${value}`,
    );

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ value: parseFloat(value) }),
    });

    if (!response.ok) {
      throw new Error(`Failed to set setpoint: ${response.statusText}`);
    }

    console.log(`[setSetpoint] Success for ${deviceId}`);
    return await response.json();
  } catch (error) {
    console.error("Error setting setpoint:", error);
    throw error;
  }
}

/**
 * Connect to WebSocket for real-time uplink events
 * @param {function} onUplinkReceived - Callback function when uplink is received
 * @returns {Promise} Promise that resolves to Socket IO client connection
 */
export function connectWebSocket(onUplinkReceived) {
  return import("socket.io-client")
    .then(({ io: ioClient }) => {
      const createNoopSocket = () => ({
        connected: false,
        on: () => {},
        off: () => {},
        emit: () => {},
        disconnect: () => {},
      });

      try {
        const socket = ioClient(API_BASE_URL, {
          autoConnect: false,
          reconnection: false,
        });

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 1500);
        return fetch(`${API_BASE_URL}/health`, {
          method: "GET",
          signal: controller.signal,
        })
          .then((res) => {
            clearTimeout(timeout);
            try {
              socket.connect();
            } catch (e) {
              console.error(
                "Socket connect failed after reachability check",
                e,
              );
              return createNoopSocket();
            }

            socket.on("connect", () => {
              console.log("Connected to broker WebSocket");
            });

            socket.on("uplink", (data) => {
              console.log("Received uplink:", data);
              if (onUplinkReceived) {
                onUplinkReceived(data);
              }
            });

            socket.on("initial", (data) => {
              console.log("Initial broker state:", data);
            });

            socket.on("disconnect", () => {
              console.log("Disconnected from broker WebSocket");
            });

            return socket;
          })
          .catch((err) => {
            clearTimeout(timeout);
            console.debug("Backend not reachable, returning noop socket", err);
            return createNoopSocket();
          });
      } catch (error) {
        console.error("Error creating socket.io client:", error);
        return createNoopSocket();
      }
    })
    .catch((error) => {
      console.error("Error importing socket.io-client:", error);
      return {
        connected: false,
        on: () => {},
        off: () => {},
        emit: () => {},
        disconnect: () => {},
      };
    });
}

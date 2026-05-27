import React, { useState, useEffect, useMemo } from "react";
import { DeviceStatusPanel } from "./components/DeviceStatusPanel";
import { LogTable } from "./components/LogTable";
import { FlowChart } from "./components/FlowChart";
import { RefreshCcw } from "lucide-react";

import {
  fetchNodes,
  fetchDeviceMetrics,
  fetchDeviceLogs,
  connectWebSocket,
  refreshData,
  sendStartSession,
  fetchSessionState,
  saveSessionState,
  saveSelectedGas,
} from "./services/api";

const PRIMARY_DEVICE_IDS = ["dev_01", "dev_02", "dev_03", "dev_04", "dev_05", "dev_06"];

function filterNodesToPrimaryDevices(nodes) {
  if (!Array.isArray(nodes)) return [];
  return nodes
    .map((node) => ({
      ...node,
      devices: Array.isArray(node?.devices)
        ? node.devices.filter((d) => PRIMARY_DEVICE_IDS.includes(d?.id))
        : [],
    }))
    .filter((node) => node.devices.length > 0);
}

const MOCK_NODES = [
  {
    id: "node_01",
    name: "MFC-1",
    status: "online",
    type: "Gas Meter",
    devices: [
      {
        id: "dev_01",
        name: "MFC-BL",
        status: "online",
        type: "Gas Meter",
      },
    ],
  },
  {
    id: "node_02",
    name: "MFC-2",
    status: "online",
    type: "Gas Meter",
    devices: [
      {
        id: "dev_02",
        name: "MFC-BK",
        status: "online",
        type: "Gas Meter",
      },
    ],
  },
];
const MOCK_METRICS = {
  dev_01: {
    signal: -85,
    battery: 87,
    uptime: "14d 3h",
    lastSeen: "2 mins ago",
  },
  dev_02: {
    signal: -65,
    battery: 100,
    uptime: "45d 12h",
    lastSeen: "Just now",
  },
  dev_03: {
    signal: -65,
    battery: 100,
    uptime: "45d 12h",
    lastSeen: "Just now",
  },
  dev_04: {
    signal: -65,
    battery: 100,
    uptime: "45d 12h",
    lastSeen: "Just now",
  },
  dev_05: {
    signal: -65,
    battery: 100,
    uptime: "45d 12h",
    lastSeen: "Just now",
  },
  dev_06: {
    signal: -65,
    battery: 100,
    uptime: "45d 12h",
    lastSeen: "Just now",
  },
};
const MOCK_LOGS = [
  {
    id: "1",
    timestamp: "2023-10-24 14:32:01",
    type: "info",
    message: "Uplink received",
    payload: "01 4A 2B",
  },
  {
    id: "2",
    timestamp: "2023-10-24 14:15:00",
    type: "success",
    message: "Join request accepted",
  },
  {
    id: "3",
    timestamp: "2023-10-24 13:45:22",
    type: "warning",
    message: "High latency detected",
    payload: "500ms",
  },
  {
    id: "4",
    timestamp: "2023-10-24 12:30:05",
    type: "info",
    message: "Periodic status update",
    payload: "AA BB CC",
  },
  {
    id: "5",
    timestamp: "2023-10-24 10:15:00",
    type: "error",
    message: "Packet loss detected",
  },
];
export function App() {
  const [nodes, setNodes] = useState([]);
  const [activeDeviceId, setActiveDeviceId] = useState(null);
  // Store metrics per device: { [deviceId]: { flow, setpoint, gases, ... } }
  const [metrics, setMetrics] = useState({});
  const [chartBuffers, setChartBuffers] = useState({});
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [socket, setSocket] = useState(null);
  const [sessionActive, setSessionActive] = useState(false);
  const [selectedGases, setSelectedGases] = useState({});
  const [deviceGasOptions, setDeviceGasOptions] = useState({});
  const [invalidGasDeviceIds, setInvalidGasDeviceIds] = useState({});
  const [sessionWarning, setSessionWarning] = useState(null);
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [refreshStatus, setRefreshStatus] = useState(null);
  const [refreshMessage, setRefreshMessage] = useState("");

  const mfcIdToDeviceId = (mfcId) => {
    const idx = Number(mfcId);
    if (!Number.isInteger(idx) || idx < 0 || idx > 5) return null;
    return `dev_${String(idx + 1).padStart(2, "0")}`;
  };

  const DEVICE_SENSORS = useMemo(() => {
    const map = {};
    PRIMARY_DEVICE_IDS.forEach((deviceId, idx) => {
      map[deviceId] = [{ id: `mfc${idx}`, label: `MFC-${idx + 1}` }];
    });
    return map;
  }, []);
  function useLiveNodeUpdates(nodes, setNodes, socket) {
    useEffect(() => {
      if (!socket) return;
      function handleUplink(uplink) {
        if (!uplink) return;
        const resolvedDeviceId = uplink.deviceId || mfcIdToDeviceId(uplink.mfcId);
        if (!resolvedDeviceId) return;
        setNodes((prevNodes) => {
          return prevNodes.map((node) => {
            if (!node.devices) return node;
            return {
              ...node,
              devices: node.devices.map((dev) =>
                dev.id === resolvedDeviceId
                  ? {
                      ...dev,
                      ...(uplink.device ? { name: `MFC-${uplink.device}` } : {}),
                      status: "online",
                    }
                  : dev,
              ),
            };
          });
        });
      }
      socket.on("uplink", handleUplink);
      return () => {
        socket.off("uplink", handleUplink);
      };
    }, [socket, setNodes]);
  }

  const [visibleSensors, setVisibleSensors] = useState(() => {
    
    const obj = {};
    Object.keys(DEVICE_SENSORS).forEach((d) => {
      obj[d] = DEVICE_SENSORS[d].map((s) => s.id);
    });
    return obj;
  });

  useEffect(() => {
    const loadNodes = async () => {
      try {
        setLoading(true);
        const data = await fetchNodes();
        const filteredNodes = filterNodesToPrimaryDevices(data);
        setNodes(filteredNodes);
        
        if (filteredNodes.length > 0) {
          if (filteredNodes[0].devices && filteredNodes[0].devices.length > 0) {
            setActiveDeviceId(filteredNodes[0].devices[0].id);
          } else {
            setActiveDeviceId(null);
          }
        } else {
          setActiveDeviceId(null);
        }
      } catch (err) {
        setError(err.message);
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    loadNodes();

    const loadSessionState = async () => {
      try {
        const state = await fetchSessionState();
        if (state && typeof state === "object") {
          setSessionActive(!!state.sessionActive);
          setSelectedGases(
            state.selectedGases && typeof state.selectedGases === "object"
              ? state.selectedGases
              : {},
          );
        }
      } catch (err) {
        console.warn("Failed to load shared session state:", err);
      }
    };

    loadSessionState();

    connectWebSocket((uplink) => {
      console.log("Received uplink:", uplink);

      if (uplink && uplink.type === "status") {
        const deviceId = uplink.deviceId || mfcIdToDeviceId(uplink.mfcId);

        if (deviceId) {
          setMetrics((prev) => ({
            ...prev,
            [deviceId]: {
              ...(prev[deviceId] || {}),
              ...(uplink.device ? { name: uplink.device } : {}),
              flow: Number.isFinite(Number(uplink.flow))
                ? Number(uplink.flow)
                : (prev[deviceId]?.flow ?? 0),
              setpoint: Number.isFinite(Number(uplink.setpoint))
                ? Number(uplink.setpoint)
                : (prev[deviceId]?.setpoint ?? 0),
            },
          }));
        }
      }
      const newLog = {
        id: String(Date.now()),
        timestamp: new Date().toLocaleString(),
        type: uplink.type || "info",
        message: uplink.message || JSON.stringify(uplink),
        payload: uplink.payload,
      };
      setLogs((prev) => [newLog, ...prev.slice(0, 199)]);
    })
      .then((newSocket) => {
        setSocket(newSocket);
      })
      .catch((err) => {
        console.error("Failed to connect to broker:", err);
      });

    return () => {
      if (socket) {
        socket.disconnect();
      }
    };
  }, []);

  useEffect(() => {
    if (!socket) return;

    const handleSessionState = (data) => {
      if (!data || typeof data !== "object") return;
      if (typeof data.sessionActive === "boolean") {
        setSessionActive(data.sessionActive);
      }
      if (data.selectedGases && typeof data.selectedGases === "object") {
        setSelectedGases(data.selectedGases);
      }
    };

    const handleMetricsUpdate = (payload) => {
      if (!payload || !payload.deviceId) return;
      setMetrics((prev) => ({
        ...prev,
        [payload.deviceId]: {
          ...(prev[payload.deviceId] || {}),
          ...(payload.name ? { name: payload.name } : {}),
          flow: Number.isFinite(Number(payload.flow))
            ? Number(payload.flow)
            : (prev[payload.deviceId]?.flow ?? 0),
          setpoint: Number.isFinite(Number(payload.setpoint))
            ? Number(payload.setpoint)
            : (prev[payload.deviceId]?.setpoint ?? 0),
        },
      }));
    };

    const handleDeviceUpdate = (payload) => {
      if (!payload || !payload.deviceId) return;
      setNodes((prevNodes) =>
        prevNodes.map((node) => ({
          ...node,
          devices: (node.devices || []).map((dev) =>
            dev.id === payload.deviceId
              ? {
                  ...dev,
                  ...(payload.name ? { name: payload.name } : {}),
                  ...(payload.status ? { status: payload.status } : {}),
                }
              : dev,
          ),
        })),
      );
    };

    const handleStateSync = (payload) => {
      if (!payload || typeof payload !== "object") return;
      if (Array.isArray(payload.nodes) && payload.nodes.length > 0) {
        setNodes(filterNodesToPrimaryDevices(payload.nodes));
      }
      if (payload.metrics && typeof payload.metrics === "object") {
        setMetrics((prev) => ({ ...prev, ...payload.metrics }));
      }
      if (Array.isArray(payload.logs)) {
        setLogs(payload.logs);
      }
      if (payload.session && typeof payload.session === "object") {
        if (typeof payload.session.sessionActive === "boolean") {
          setSessionActive(payload.session.sessionActive);
        }
        if (
          payload.session.selectedGases &&
          typeof payload.session.selectedGases === "object"
        ) {
          setSelectedGases(payload.session.selectedGases);
        }
      }
    };

    const handleSessionUpdated = (payload) => {
      if (!payload || typeof payload !== "object") return;
      if (typeof payload.sessionActive === "boolean") {
        setSessionActive(payload.sessionActive);
      }
      if (payload.selectedGases && typeof payload.selectedGases === "object") {
        setSelectedGases(payload.selectedGases);
      }
    };

    const handleGasSelected = (payload) => {
      if (!payload || !payload.deviceId) return;
      setSelectedGases((prev) => ({
        ...prev,
        [payload.deviceId]: payload.gas,
      }));
      setInvalidGasDeviceIds((prev) => {
        if (!prev[payload.deviceId]) return prev;
        const next = { ...prev };
        delete next[payload.deviceId];
        return next;
      });
    };

    const handleSessionReset = () => {
      setSessionActive(false);
      setInvalidGasDeviceIds({});
      setSessionWarning(null);
    };

    const handleDataRefreshed = (payload) => {
      if (!payload || typeof payload !== "object") return;
      const devices = payload.devices;
      if (devices && typeof devices === "object") {
        setMetrics((prev) => {
          const next = { ...prev };
          Object.entries(devices).forEach(([deviceId, data]) => {
            next[deviceId] = {
              ...(prev[deviceId] || {}),
              flow: Number.isFinite(Number(data?.flow))
                ? Number(data.flow)
                : (prev[deviceId]?.flow ?? 0),
              setpoint: Number.isFinite(Number(data?.setpoint))
                ? Number(data.setpoint)
                : (prev[deviceId]?.setpoint ?? 0),
              ...(data?.name ? { name: data.name } : {}),
              ...(data?.status ? { status: data.status } : {}),
            };
          });
          return next;
        });
      }
    };

    socket.on("session-state", handleSessionState);
    socket.on("session_started", handleSessionUpdated);
    socket.on("session_updated", handleSessionUpdated);
    socket.on("metrics-update", handleMetricsUpdate);
    socket.on("device-update", handleDeviceUpdate);
    socket.on("state-sync", handleStateSync);
    socket.on("gas_selected", handleGasSelected);
    socket.on("session_reset", handleSessionReset);
    socket.on("data_refreshed", handleDataRefreshed);
    return () => {
      socket.off("session-state", handleSessionState);
      socket.off("session_started", handleSessionUpdated);
      socket.off("session_updated", handleSessionUpdated);
      socket.off("metrics-update", handleMetricsUpdate);
      socket.off("device-update", handleDeviceUpdate);
      socket.off("state-sync", handleStateSync);
      socket.off("gas_selected", handleGasSelected);
      socket.off("session_reset", handleSessionReset);
      socket.off("data_refreshed", handleDataRefreshed);
    };
  }, [socket]);

  useEffect(() => {
    const availableDeviceIds = nodes.flatMap((node) =>
      Array.isArray(node?.devices)
        ? node.devices
            .map((d) => d.id)
            .filter((id) => PRIMARY_DEVICE_IDS.includes(id))
        : [],
    );

    if (!availableDeviceIds.length) {
      setActiveDeviceId(null);
      return;
    }

    if (!activeDeviceId || !availableDeviceIds.includes(activeDeviceId)) {
      setActiveDeviceId(availableDeviceIds[0]);
    }
  }, [nodes, activeDeviceId]);

  useEffect(() => {
    const loadMetrics = async () => {
      try {
        setLoading(true);

        const data = await fetchDeviceMetrics(activeDeviceId);

        console.log(`[App] Fetched metrics for ${activeDeviceId}:`, data);

        setMetrics((prev) => ({
          ...prev,
          [activeDeviceId]: { ...data },
        }));
        setError(null);
      } catch (err) {
        const message = String(err?.message || "");
        if (message.includes("Failed to fetch metrics: Not Found")) {
          console.warn("Skipping metrics fetch for unavailable device", activeDeviceId);
          return;
        }
        setError(message || "Failed to fetch metrics");
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    if (activeDeviceId) {
      loadMetrics();
    }
  }, [activeDeviceId]);

  useEffect(() => {
    const loadLogs = async () => {
      try {
        const data = await fetchDeviceLogs(activeDeviceId);
        setLogs(data || MOCK_LOGS);
        setError(null);
      } catch (err) {
        const message = String(err?.message || "");
        if (message.includes("Failed to fetch logs: Not Found")) {
          console.warn("Skipping logs fetch for unavailable device", activeDeviceId);
          return;
        }
        setError(message || "Failed to fetch logs");
        console.error(err);
      }
    };
    if (activeDeviceId) {
      loadLogs();
    }
  }, [activeDeviceId]);

  useEffect(() => {
    if (refreshStatus !== "success") return;

    const timerId = setTimeout(() => {
      setRefreshStatus(null);
      setRefreshMessage("");
    }, 3000);

    return () => clearTimeout(timerId);
  }, [refreshStatus]);


  const allDevices = nodes.flatMap((node) => {
    if (node?.type === "Wind Sensor") return [];
    return Array.isArray(node?.devices)
      ? node.devices.filter((d) => PRIMARY_DEVICE_IDS.includes(d?.id))
      : [];
  });

  const handleStartSession = async () => {
    const requiresGasSelection = (deviceId) => {
      const options = deviceGasOptions[deviceId];
      return Array.isArray(options) && options.length > 0;
    };

    const missingGasDevices = allDevices.filter(
      (dev) => requiresGasSelection(dev.id) && !selectedGases[dev.id],
    );

    if (missingGasDevices.length > 0) {
      const invalidMap = Object.fromEntries(
        missingGasDevices.map((dev) => [dev.id, true]),
      );
      setInvalidGasDeviceIds(invalidMap);
      setSessionWarning(
        "Select a gas for every connected device before starting the session.",
      );
      return;
    }

    setInvalidGasDeviceIds({});
    setSessionWarning(null);
    setLoading(true);
    try {
      
      const selections = [];
      allDevices.forEach((dev) => {
        const gas = selectedGases[dev.id];
        if (gas) {
          selections.push({ deviceId: dev.id, gas });
        }
      });
      await sendStartSession(selections);
      setSessionActive(true);
      console.log("Sent start session for all devices:", selections);
    } catch (err) {
      setError("Failed to start session: " + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  const handleResetSession = async () => {
    setLoading(true);
    try {
      await saveSessionState({ sessionActive: false, selectedGases });
      setSessionActive(false);
      setInvalidGasDeviceIds({});
      setSessionWarning(null);
      console.log("Resetting shared session state");
    } catch (err) {
      setError("Failed to reset session state: " + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }

    // try {
    //   setSessionActive(false);
    //   setLoading(true);
    //   const deviceToMfcId = (id) => {
    //     if (id === "dev_01") return 1;
    //     if (id === "dev_02") return 0;
    //     return null;
    //   };
    //   const mfc = deviceToMfcId(activeDeviceId);
    //   await resetSession({ mfc });
    //   setMetrics({ flow: 0, setpoint: 0 });
    //   setChartBuffers({});
    //   setLogs([]);
    // } catch (error) {
    //   console.error("Error setting setpoint:", error);
    // } finally {
    //   setLoading(false);
    // }
  };

  const handleRefreshData = async () => {
    setRefreshLoading(true);
    setRefreshStatus(null);
    setRefreshMessage("");
    let timeoutId;

    try {
      const timeoutPromise = new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          reject(new Error("Failed to refresh after 30 seconds"));
        }, 30000);
      });

      const result = await Promise.race([refreshData(), timeoutPromise]);

      if (result?.devices && typeof result.devices === "object") {
        setMetrics((prev) => {
          const next = { ...prev };
          Object.entries(result.devices).forEach(([deviceId, data]) => {
            next[deviceId] = {
              ...(prev[deviceId] || {}),
              flow: Number.isFinite(Number(data?.flow))
                ? Number(data.flow)
                : (prev[deviceId]?.flow ?? 0),
              setpoint: Number.isFinite(Number(data?.setpoint))
                ? Number(data.setpoint)
                : (prev[deviceId]?.setpoint ?? 0),
              ...(data?.name ? { name: data.name } : {}),
              ...(data?.status ? { status: data.status } : {}),
            };
          });
          return next;
        });
      }

      setRefreshStatus("success");
      setRefreshMessage("Data refreshed successfully.");
    } catch (err) {
      setRefreshStatus("error");
      setRefreshMessage(err?.message || "Failed to refresh data.");
    } finally {
      clearTimeout(timeoutId);
      setRefreshLoading(false);
    }
  };

  useLiveNodeUpdates(nodes, setNodes, socket);

  return error ? (
    <div className="min-h-screen bg-[#f8fafc] flex items-center justify-center">
      <div className="text-red-600">Error: {error}</div>
    </div>
  ) : (
    <div className="min-h-screen bg-[#f8fafc] text-slate-900 font-sans">
      <main className="max-w-8xl mx-auto px-8 py-8">
        {/* Top Grid: Status & Location */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6 sm:flex-row flex-col">
            <div className="grid grid-cols-2 lg:space-x-8 lg:gap-0 gap-6 sm:mb-4 mb-4">
              <h2 className="text-xl font-bold text-slate-900">
                Device Overview
              </h2>
              <button
                onClick={handleRefreshData}
                disabled={refreshLoading}
                className={`
                  inline-flex items-center px-4 py-2 
                  bg-blue-500 text-white text-sm font-medium rounded-full
                  transition-colors shadow-sm
                  hover:bg-blue-600 hover:shadow

                  disabled:bg-orange-300
                  disabled:hover:bg-orange-300
                  disabled:hover:shadow-none
                  disabled:cursor-not-allowed

                
                `}
              >
                <RefreshCcw className={`w-5 h-5 mr-2 ${refreshLoading ? "animate-spin" : ""}`} />
                {refreshLoading ? "Refreshing..." : "Refresh Data"}
              </button>
            </div>

            <div className="space-x-8">
              <button
                onClick={handleStartSession}
                disabled={loading || sessionActive}
                className="
                px-3 py-1.5 border text-sm font-medium rounded-md shadow-sm transition-colors
                bg-green-500 text-white border-green-500
                hover:bg-green-600
                hover:border-green-600

                disabled:bg-white
                disabled:text-green-200
                disabled:border-green-200
                disabled:hover:bg-white
                disabled:cursor-not-allowed
                "
              >
                {loading ? "Sending..." : "Set Gas"}
              </button>

              <button
                onClick={handleResetSession}
                disabled={loading || !sessionActive}
                className="
                px-3 py-1.5 border text-sm font-medium rounded-md shadow-sm transition-colors
                bg-orange-500 text-white border-orange-500
                hover:bg-orange-600
                hover:border-orange-600

                disabled:bg-white
                disabled:text-orange-200
                disabled:border-orange-200
                disabled:hover:bg-white
                disabled:cursor-not-allowed
                "
              >
                {loading ? "Sending..." : "Change Gas"}
              </button>
            </div>
          </div>
          {refreshStatus === "success" && (
            <div className="mb-4 rounded-md border border-green-200 bg-green-50 px-4 py-2 text-sm text-green-700">
              {refreshMessage}
            </div>
          )}
          {refreshStatus === "error" && (
            <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              {refreshMessage}
            </div>
          )}
          {sessionWarning && (
            <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              {sessionWarning}
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {allDevices.map((dev) => (
                <DeviceStatusPanel
                  device={dev}
                  key={dev.id}
                  socket={socket}
                  activeDeviceId={dev.id}
                  sessionActive={sessionActive}
                  onError={setError}
                  metrics={metrics[dev.id] || { flow: 0, setpoint: 0 }}
                  cachedGasOptions={deviceGasOptions[dev.id] || []}
                  selectedGas={selectedGases[dev.id]}
                  onGasOptionsLoaded={(options) => {
                    setDeviceGasOptions((prev) => ({
                      ...prev,
                      [dev.id]: Array.isArray(options) ? options : [],
                    }));
                  }}
                  onSelectGas={(gas) => {
                    setSelectedGases((prev) => ({ ...prev, [dev.id]: gas }));
                    saveSelectedGas(dev.id, gas).catch((err) => {
                      console.error("Failed to sync selected gas:", err);
                      setError("Failed to sync selected gas: " + err.message);
                    });
                    setInvalidGasDeviceIds((prev) => {
                      if (!prev[dev.id]) return prev;
                      const next = { ...prev };
                      delete next[dev.id];
                      return next;
                    });
                    setSessionWarning(null);
                  }}
                  gasSelectionError={!!invalidGasDeviceIds[dev.id]}
                  onDataUpdate={(buffer) =>
                    setChartBuffers((prev) => ({
                      ...prev,
                      [dev.id]: buffer,
                    }))
                  }
                  onMetricsUpdate={setMetrics}
                />
              ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
          {/* Left Column: Commands & Location */}
          <div className="lg:col-span-1 space-y-8">
            <div className="lg:col-span-2">
              <LogTable logs={logs} />
            </div>
            {/* <div className="h-64">
              <LocationCard
                lat={37.7749}
                lng={-122.4194}
                address="Building 4, Server Room B"
              />
            </div> */}
          </div>
          <div className="mb-8 lg:col-span-2">
            <FlowChart
              deviceId={activeDeviceId}
              initialData={chartBuffers[activeDeviceId]}
              sensors={visibleSensors[activeDeviceId] || []}
              onMetricsUpdate={setMetrics}
              onDataUpdate={(buffer) =>
                setChartBuffers((prev) => ({
                  ...prev,
                  [activeDeviceId]: buffer,
                }))
              }
            />
          </div>
        </div>
      </main>
    </div>
  );
}

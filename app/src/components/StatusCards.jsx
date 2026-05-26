import React, { useState, useEffect, useRef } from "react";
import { connectWebSocket, fetchDeviceMetrics } from "../services/api";
import DropdownButton from "./DropdownButton";
import {
  Signal,
  Battery,
  Clock,
  Wifi,
  Zap,
  Activity,
  Gauge,
  CircleGauge,
} from "lucide-react";

const METRICS_FALLBACK_INTERVAL_MS = 30000;

export function StatusCards({    
  metrics,
  socket,
  activeDeviceId,
  sessionActive,
  sensors = [],
  gasOptions,
  selectedGas,
  onSelectGas,
  gasSelectionError = false,
  onMetricsUpdate,
  onDataUpdate,
}) {
  const socketRef = useRef(null);
  const [data, setData] = useState([]);
  const [connected, setConnected] = useState(false);
  const safeMetrics = metrics && typeof metrics === 'object' ? metrics : { flow: 0, setpoint: 0, gases: [] };
  const [localSensorMetrics, setLocalSensorMetrics] = useState(() => {
    const map = {};
    (sensors || []).forEach((id) => {
      map[id] = { flow: 0, setpoint: 0 };
    });
    return map;
  });

  const deviceToMfcId = (id) => {
    if (id === "dev_01") return 0; // MFC-BL
    if (id === "dev_02") return 1; // MFC-BK
    return null;
  };

  const mfcIdToDevice = {
      0: "dev_01",
      1: "dev_02",
    };

  useEffect(() => {
    
    setLocalSensorMetrics((prev) => {
      const copy = { ...prev };
      (sensors || []).forEach((id) => {
        if (!copy[id]) copy[id] = { flow: 0, setpoint: 0 };
      });
      Object.keys(copy).forEach((k) => {
        if (!(sensors || []).includes(k)) delete copy[k];
      });
      const prevKeys = Object.keys(prev || {});
      const copyKeys = Object.keys(copy);
      if (prevKeys.length === copyKeys.length) {
        let same = true;
        for (const k of copyKeys) {
          const a = copy[k];
          const b = prev[k];
          if (!b || a.flow !== b.flow || a.setpoint !== b.setpoint) {
            same = false;
            break;
          }
        }
        if (same) return prev;
      }
      return copy;
    });
  }, [sensors]);

  const getDeviceAccentClass = (deviceId) => {
    const palette = ["text-blue-500", "text-emerald-500", "text-violet-500", "text-amber-500", "text-cyan-500"];
    if (typeof deviceId !== "string") return palette[0];
    const match = /^dev_(\d+)$/i.exec(deviceId.trim());
    const idx = match ? Number.parseInt(match[1], 10) - 1 : 0;
    if (!Number.isInteger(idx) || idx < 0) return palette[0];
    return palette[idx % palette.length];
  };

  const getFlowColor = (dbm) => {
    if (!sessionActive) return "text-orange-500";
    return getDeviceAccentClass(activeDeviceId);
  };
  const getSetpointColor = (level) => {
    if (!sessionActive) return "text-orange-500";
    return getDeviceAccentClass(activeDeviceId);
  };

  const formatMetricValue = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "0.0";
    if (numeric === 0) return "0.0";
    const raw = String(value).trim();
    if (raw.startsWith("0.0")) return "0.0";
    return raw;
  };

  useEffect(() => {
      let unsubSocket = null;
      const lastMetricsFetch = { t: 0 };
      connectWebSocket((uplink) => {
        try {
          console.debug("FlowChart uplink raw:", uplink);
  
          if (uplink && uplink.type === "status") {
            const uplinkMfc = Number(uplink.mfcId);
            const flow = parseFloat(uplink.flow);
            const setpoint = parseFloat(uplink.setpoint);
            const ts = Date.now();
  
            setData((prev) => {
              const last = prev[prev.length - 1] || {};
              const newPoint = {
                time: new Date(ts).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
                timestamp: ts,
                flow_mfc0: last.flow_mfc0 || 0,
                setpoint_mfc0: last.setpoint_mfc0 || 0,
                flow_mfc1: last.flow_mfc1 || 0,
                setpoint_mfc1: last.setpoint_mfc1 || 0,
              };

              if (uplinkMfc === 0) {
                newPoint.flow_mfc0 = Number.isFinite(flow) ? flow : 0;
                newPoint.setpoint_mfc0 = Number.isFinite(setpoint) ? setpoint : 0;
              } else if (uplinkMfc === 1) {
                newPoint.flow_mfc1 = Number.isFinite(flow) ? flow : 0;
                newPoint.setpoint_mfc1 = Number.isFinite(setpoint) ? setpoint : 0;
              }
              const next = [...prev.slice(1), newPoint];
              try {
                saveBuffer(next);
              } catch (e) {
                console.debug("saveBuffer failed", e);
              }
              if (onDataUpdate) onDataUpdate(next);
              if (onMetricsUpdate) {
                const curMfc = deviceToMfcId(activeDeviceId);
                if (curMfc === uplinkMfc)
                  onMetricsUpdate((prev) => ({
                    ...prev,
                    [activeDeviceId]: {
                      ...(prev[activeDeviceId] || {}),
                      flow: newPoint[`flow_mfc${uplinkMfc}`],
                      setpoint: newPoint[`setpoint_mfc${uplinkMfc}`],
                    },
                  }));
              }
              return next;
            });
            return;
          }
  
          const now = Date.now();
          if (now - lastMetricsFetch.t > METRICS_FALLBACK_INTERVAL_MS) {
            lastMetricsFetch.t = now;
            Promise.all(
              Object.values(mfcIdToDevice).map((dev) =>
                fetchDeviceMetrics(dev).catch(() => null),
              ),
            )
              .then((results) => {
                const ts = Date.now();
                setData((prev) => {
                  const last = prev[prev.length - 1] || {};
                  const newPoint = {
                    time: new Date(ts).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    }),
                    timestamp: ts,
                    flow_mfc0: last.flow_mfc0 || 0,
                    setpoint_mfc0: last.setpoint_mfc0 || 0,
                    flow_mfc1: last.flow_mfc1 || 0,
                    setpoint_mfc1: last.setpoint_mfc1 || 0,
                  };
                  const res0 = results[0];
                  const res1 = results[1];
                  if (res0) {
                    const fv = parseFloat(res0.flow);
                    const sv = parseFloat(res0.setpoint);
                    newPoint.flow_mfc0 = Number.isFinite(fv)
                      ? fv
                      : newPoint.flow_mfc0;
                    newPoint.setpoint_mfc0 = Number.isFinite(sv)
                      ? sv
                      : newPoint.setpoint_mfc0;
                  }
                  if (res1) {
                    const fv = parseFloat(res1.flow);
                    const sv = parseFloat(res1.setpoint);
                    newPoint.flow_mfc1 = Number.isFinite(fv)
                      ? fv
                      : newPoint.flow_mfc1;
                    newPoint.setpoint_mfc1 = Number.isFinite(sv)
                      ? sv
                      : newPoint.setpoint_mfc1;
                  }
                  const next = [...prev.slice(1), newPoint];
                  try {
                    saveBuffer(next);
                  } catch (e) {
                    console.debug("saveBuffer failed", e);
                  }
                  if (onDataUpdate) onDataUpdate(next);
                  if (onMetricsUpdate) {
                    const cur = deviceToMfcId(activeDeviceId);
                    onMetricsUpdate((prev) => ({
                      ...prev,
                      [activeDeviceId]: {
                        ...(prev[activeDeviceId] || {}),
                        flow: newPoint[`flow_mfc${cur}`],
                        setpoint: newPoint[`setpoint_mfc${cur}`],
                      },
                    }));
                  }
                  return next;
                });
              })
              .catch((err) => {
                console.debug("FlowChart metrics fallback failed", err);
              });
          }
        } catch (e) {
          console.error("FlowChart parse error", e);
        }
      })
        .then((socket) => {
          socketRef.current = socket;
          unsubSocket = socket;
          setConnected(!!socket.connected);
          socket.on("connect", () => setConnected(true));
          socket.on("disconnect", () => setConnected(false));
          socket.on("connect_error", (err) => {
            console.error("FlowChart socket connect_error", err);
            setConnected(false);
          });
        })
        .catch((err) => {
          console.error("FlowChart websocket error", err);
          setConnected(false);
        });
  
      return () => {
        if (socketRef.current) {
          socketRef.current.disconnect();
          socketRef.current = null;
        }
        unsubSocket = null;
      };
    }, [activeDeviceId]);

  // Auto-update display from safeMetrics
  useEffect(() => {
    setData((prev) => {
      const ts = Date.now();
      const newPoint = {
        time: new Date(ts).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        timestamp: ts,
        flow_mfc0: prev[prev.length - 1]?.flow_mfc0 || 0,
        setpoint_mfc0: safeMetrics.setpoint_mfc0 || 0,
        flow_mfc1: prev[prev.length - 1]?.flow_mfc1 || 0,
        setpoint_mfc1: safeMetrics.setpoint_mfc1 || 0,
      };
      return [...prev.slice(1), newPoint];
    });
  }, [safeMetrics.flow, safeMetrics.setpoint]);

  return (
    <div className="grid grid-rows-1 md:grid-rows-2 gap-6 ">
      {/* Signal Card */}
      <div className="bg-white  p-6  shadow-sm">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-sm font-medium text-slate-500 mb-1">Flow Rate</p>
            <h3 className="text-2xl font-bold text-slate-900">
              {formatMetricValue(safeMetrics.flow)} <span className="text-sm font-normal text-slate-400">ln/min</span>
            </h3>
          </div>
          <div
            className={`p-3 bg-slate-50 rounded-lg ${getFlowColor(safeMetrics.flow)}`}
          >
            <Gauge className="w-6 h-6" />
          </div>
        </div>
        <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${getFlowColor(safeMetrics.flow).replace("text-", "bg-")}`}
            style={{
              width: `${Math.min(100, Math.max(0, (120 + (safeMetrics.flow.toString().slice(0, 4) === "0.0" ? 0 : safeMetrics.flow)) * 2))}%`,
            }}
          />
        </div>
        <div className="flex items-center gap-2 mt-4">
          <span className="text-sm font-normal text-slate-400">GAS:</span>
          <DropdownButton
            selected={selectedGas}
            onChange={onSelectGas}
            sessionActive={sessionActive}
            gasOptions={gasOptions}
            hasError={gasSelectionError}
          />
        </div>
      </div>


      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-sm font-medium text-slate-500 mb-1">Setpoint</p>
            <h3 className="text-2xl font-bold text-slate-900">
              {formatMetricValue(safeMetrics.setpoint)} <span className="text-sm font-normal text-slate-400">ln/min</span>
            </h3>
          </div>
          <div
            className={`p-3 bg-slate-50 rounded-lg ${getSetpointColor(safeMetrics.setpoint)}`}
          >
            <CircleGauge className="w-6 h-6" />
          </div>
        </div>
        <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${getSetpointColor(safeMetrics.setpoint).replace("text-", "bg-")}`}
            style={{
              width: `${Math.min(100, Math.max(0, (120 + (safeMetrics.setpoint.toString().slice(0, 4) === "0.0" ? 0 : safeMetrics.setpoint)) * 2))}%`,
            }}
          />
        </div>
      </div>
    </div>
  );
  
}

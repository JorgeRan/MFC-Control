import React, { useState, useEffect, useRef } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { TrendingUp } from "lucide-react";

import { connectWebSocket, fetchDeviceMetrics } from "../services/api";

const METRICS_FALLBACK_INTERVAL_MS = 30000;
const MAX_MFC_DEVICES = 6;

export function FlowChart({
  deviceId,
  onMetricsUpdate,
  initialData,
  onDataUpdate,
  sensors = ["mfc0", "mfc1"],
}) {
  const [data, setData] = useState([]);
  const socketRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [visibleMap, setVisibleMap] = useState(() => {
    const m = {};
    (sensors || []).forEach((s) => (m[s] = true));
    return m;
  });

  const deviceToMfcId = (id) => {
    const match = /^dev_(\d+)$/i.exec(String(id || "").trim());
    if (!match) return null;
    const idx = Number.parseInt(match[1], 10) - 1;
    if (!Number.isInteger(idx) || idx < 0 || idx >= MAX_MFC_DEVICES) return null;
    return idx;
  };
  const mfcIdToDevice = Object.fromEntries(
    Array.from({ length: MAX_MFC_DEVICES }, (_, idx) => [idx, `dev_${String(idx + 1).padStart(2, "0")}`]),
  );

  const STORAGE_KEY = "flowchart_buffer";

  const saveBuffer = (buf) => {
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(buf));
      }
    } catch (e) {
      console.debug("FlowChart saveBuffer failed", e);
    }
  };

  useEffect(() => {
    const now = Date.now();
    const initial = Array.from({ length: 12 }, (_, i) => {
      const point = {
        time: new Date(now - (12 - i) * 5000).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        timestamp: now - (12 - i) * 5000,
      };
      for (let idx = 0; idx < MAX_MFC_DEVICES; idx++) {
        point[`flow_mfc${idx}`] = 0;
        point[`setpoint_mfc${idx}`] = 0;
      }
      return point;
    });

    try {
      if (typeof window !== "undefined" && window.localStorage) {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setData(parsed);
            if (onDataUpdate) onDataUpdate(parsed);
            return;
          }
        }
      }
    } catch (e) {
      console.debug("FlowChart restore failed", e);
    }

    if (initialData && Array.isArray(initialData) && initialData.length > 0) {
      const curMfc = deviceToMfcId(deviceId);
      const mapped = initial.map((pt, idx) => {
        const src = initialData[idx] || {};
        const out = { ...pt };
        if (curMfc !== null) {
          out[`flow_mfc${curMfc}`] = Number.isFinite(Number(src.flow))
            ? Number(src.flow)
            : 0;
          out[`setpoint_mfc${curMfc}`] = Number.isFinite(Number(src.setpoint))
            ? Number(src.setpoint)
            : 0;
        }
        return out;
      });
      setData(mapped);
      try {
        saveBuffer(mapped);
      } catch (e) {}
      if (onDataUpdate) onDataUpdate(mapped);
    } else {
      setData(initial);
      try {
        saveBuffer(initial);
      } catch (e) {}
      if (!initialData && onDataUpdate) onDataUpdate(initial);
    }
  }, [deviceId]);

  useEffect(() => {
    if (initialData && Array.isArray(initialData) && initialData.length > 0) {
      const curMfc = deviceToMfcId(deviceId);
      setData((prev) => {
        const next = prev.slice();
        for (let i = 0; i < Math.min(next.length, initialData.length); i++) {
          const src = initialData[i];
          const cur = next[i] || {};
          if (curMfc !== null) {
            next[i] = {
              ...cur,
              [`flow_mfc${curMfc}`]: Number.isFinite(Number(src.flow))
                ? Number(src.flow)
                : cur[`flow_mfc${curMfc}`] || 0,
              [`setpoint_mfc${curMfc}`]: Number.isFinite(Number(src.setpoint))
                ? Number(src.setpoint)
                : cur[`setpoint_mfc${curMfc}`] || 0,
            };
          }
        }
        return next;
      });
    }
  }, [initialData, deviceId]);

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
            };
            for (let idx = 0; idx < MAX_MFC_DEVICES; idx++) {
              newPoint[`flow_mfc${idx}`] = last[`flow_mfc${idx}`] || 0;
              newPoint[`setpoint_mfc${idx}`] = last[`setpoint_mfc${idx}`] || 0;
            }
            if (Number.isInteger(uplinkMfc) && uplinkMfc >= 0 && uplinkMfc < MAX_MFC_DEVICES) {
              newPoint[`flow_mfc${uplinkMfc}`] = Number.isFinite(flow) ? flow : 0;
              newPoint[`setpoint_mfc${uplinkMfc}`] = Number.isFinite(setpoint) ? setpoint : 0;
            }
            const next = [...prev.slice(1), newPoint];
            try {
              saveBuffer(next);
            } catch (e) {
              console.debug("saveBuffer failed", e);
            }
            if (onDataUpdate) onDataUpdate(next);
            if (onMetricsUpdate) {
              const curMfc = deviceToMfcId(deviceId);
              if (curMfc === uplinkMfc)
                onMetricsUpdate((prev) => ({
                  ...prev,
                  [deviceId]: {
                    ...(prev[deviceId] || {}),
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
                };
                for (let idx = 0; idx < MAX_MFC_DEVICES; idx++) {
                  newPoint[`flow_mfc${idx}`] = last[`flow_mfc${idx}`] || 0;
                  newPoint[`setpoint_mfc${idx}`] = last[`setpoint_mfc${idx}`] || 0;
                }
                results.forEach((res, idx) => {
                  if (!res || idx < 0 || idx >= MAX_MFC_DEVICES) return;
                  const fv = parseFloat(res.flow);
                  const sv = parseFloat(res.setpoint);
                  newPoint[`flow_mfc${idx}`] = Number.isFinite(fv)
                    ? fv
                    : newPoint[`flow_mfc${idx}`];
                  newPoint[`setpoint_mfc${idx}`] = Number.isFinite(sv)
                    ? sv
                    : newPoint[`setpoint_mfc${idx}`];
                });

                const next = [...prev.slice(1), newPoint];
                try {
                  saveBuffer(next);
                } catch (e) {
                  console.debug("saveBuffer failed", e);
                }
                if (onDataUpdate) onDataUpdate(next);
                if (onMetricsUpdate) {
                  const cur = deviceToMfcId(deviceId);
                  onMetricsUpdate((prev) => ({
                    ...prev,
                    [deviceId]: {
                      ...(prev[deviceId] || {}),
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
  }, [deviceId]);

  const safeData =
    Array.isArray(data) && data.length > 0
      ? data
      : (() => {
          const now = Date.now();
          return Array.from({ length: 12 }, (_, i) => ({
            time: new Date(now - (12 - i) * 5000).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
            timestamp: now - (12 - i) * 5000,
            flow_mfc0: 0,
            setpoint_mfc0: 0,
            flow_mfc1: 0,
            setpoint_mfc1: 0,
          }));
        })();

  // const avgFlow =
  //   safeData.length > 0
  //     ? (safeData.reduce((sum, point) => sum + ((Number(point.flow_mfc0) || 0) + (Number(point.flow_mfc1) || 0)) / 2, 0) / safeData.length).toFixed(2)
  //     : '0.00'
  // const maxFlow = safeData.length > 0 ? Math.max(...safeData.map((p) => Math.max(Number(p.flow_mfc0) || 0, Number(p.flow_mfc1) || 0))).toFixed(2) : '0.00'
  // const minFlow = safeData.length > 0 ? Math.min(...safeData.map((p) => Math.min(Number(p.flow_mfc0) || 0, Number(p.flow_mfc1) || 0))).toFixed(2) : '0.00'

  return (
    <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-blue-50 rounded-lg">
            <TrendingUp className="w-6 h-6 text-blue-500" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900">
              Flow vs Time
            </h3>
            <p className="text-sm text-slate-500">
              Real-time flow rate monitoring
            </p>
          </div>
          <div className="ml-4">
            <span
              className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${connected ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}
            >
              {connected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
      </div>

      {/* Stats
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4">
          <p className="text-xs font-medium text-blue-600 mb-1">Average Flow</p>
          <p className="text-2xl font-bold text-blue-900">{avgFlow} <span className="text-sm font-normal text-blue-600">ln/min</span></p>
        </div>
        <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-lg p-4">
          <p className="text-xs font-medium text-emerald-600 mb-1">Max Flow</p>
          <p className="text-2xl font-bold text-emerald-900">{maxFlow} <span className="text-sm font-normal text-emerald-600">ln/min</span></p>
        </div>
        <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-lg p-4">
          <p className="text-xs font-medium text-orange-600 mb-1">Min Flow</p>
          <p className="text-2xl font-bold text-orange-900">{minFlow} <span className="text-sm font-normal text-orange-600">ln/min</span></p>
        </div>
      </div> */}

      {/* Chart */}
      <div className="bg-slate-50 rounded-lg p-4">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart
            data={safeData}
            margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
          >
            <defs>
              <linearGradient id="colorFlow" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorSetpoint" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="timestamp"
              stroke="#94a3b8"
              style={{ fontSize: "12px" }}
              domain={["dataMin", "dataMax"]}
              tickFormatter={(t) =>
                t
                  ? new Date(t).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : ""
              }
            />
            <YAxis
              stroke="#94a3b8"
              label={{
                value: "Flow (ln/min)",
                angle: -90,
                position: "insideLeft",
              }}
              style={{ fontSize: "12px" }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#1e293b",
                border: "1px solid #475569",
                borderRadius: "8px",
                color: "#f1f5f9",
              }}
              formatter={(value) =>
                value != null && !Number.isNaN(value)
                  ? Number(value).toFixed(2)
                  : "0.00"
              }
              labelStyle={{ color: "#f1f5f9" }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} iconType="line" />
            {sensors.map((sid, idx) => {
              const flowKey = `flow_${sid}`;
              const setKey = `setpoint_${sid}`;
              const flowColors = ["#3b82f6", "#10b981", "#6366f1", "#f59e0b"];
              const setColors = ["#ef4444", "#f97316", "#ef4444", "#f97316"];
              const flowStroke = flowColors[idx % flowColors.length];
              const setStroke = setColors[idx % setColors.length];
              const labelBase = sid.toUpperCase();
              return (
                <React.Fragment key={sid}>
                  <Line
                    type="monotone"
                    dataKey={flowKey}
                    stroke={flowStroke}
                    strokeWidth={2}
                    name={`${labelBase} Flow`}
                    dot={false}
                    fillOpacity={1}
                    fill="url(#colorFlow)"
                  />
                  <Line
                    type="monotone"
                    dataKey={setKey}
                    stroke={setStroke}
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    name={`${labelBase} Setpoint`}
                    dot={false}
                  />
                </React.Fragment>
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

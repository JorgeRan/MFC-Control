import React, { useState, useEffect } from "react";
import {
  Filter,
  ChevronDown,
  AlertCircle,
  Info,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
export function LogTable({ logs }) {
  const [filter, setFilter] = useState("all");
  const normalizedLogs = Array.isArray(logs)
    ? logs
    : Array.isArray(logs?.logs)
      ? logs.logs
      : [];

  const filteredLogs =
    filter === "all"
      ? normalizedLogs
      : normalizedLogs.filter((log) => log.type === filter);

  const getTypeIcon = (type) => {
    switch (type) {
      case "error":
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      case "warning":
        return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case "success":
        return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
      default:
        return <Info className="w-4 h-4 text-blue-500" />;
    }
  };
  const getTypeStyles = (type) => {
    switch (type) {
      case "error":
        return "bg-red-50 text-red-700 border-red-100";
      case "warning":
        return "bg-amber-50 text-amber-700 border-amber-100";
      case "success":
        return "bg-emerald-50 text-emerald-700 border-emerald-100";
      default:
        return "bg-blue-50 text-blue-700 border-blue-100";
    }
  };


  

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-white">
        <h3 className="text-lg font-semibold text-slate-900">Device Logs</h3>

        <div className="relative">
          <div className="flex items-center space-x-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="text-sm border-none bg-transparent focus:ring-0 text-slate-600 font-medium cursor-pointer pr-8"
            >
              <option value="all">All Events</option>
              <option value="info">Info</option>
              <option value="warning">Warnings</option>
              <option value="error">Errors</option>
              <option value="success">Success</option>
            </select>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto, overflow-y-auto max-h-96">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
            <tr>
              {/* <th className="px-6 py-3 w-48">Timestamp</th> */}
              <th className="px-6 py-3 w-32">Type</th>
              <th className="px-6 py-3">Message</th>
              <th className="px-6 py-3 text-right">Payload</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredLogs.map((log, index) => (
              <tr
                key={log.id + '-' + index}
                className={`hover:bg-slate-50 transition-colors ${index % 2 === 0 ? "bg-white" : "bg-[#f8fafc]"}`}
              >
                {/* <td className="px-6 py-3 text-slate-500 font-mono text-xs">
                  {log.timestamp}
                </td> */}
                <td className="px-6 py-3">
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getTypeStyles(log.type)}`}
                  >
                    {getTypeIcon(log.type)}
                    <span className="ml-1.5 capitalize">{log.type}</span>
                  </span>
                </td>
                <td className="px-6 py-3 text-slate-700">{log.message}</td>
                <td className="px-6 py-3 text-right">
                  {log.payload && (
                    <code className="px-2 py-1 bg-slate-100 rounded text-slate-600 text-xs font-mono border border-slate-200">
                      {log.payload}
                    </code>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredLogs.length === 0 && (
        <div className="p-8 text-center text-slate-500">
          No logs found for this filter.
        </div>
      )}
    </div>
  );
}

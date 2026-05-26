import React, { useState, useEffect, useRef } from "react";
import { StatusCards } from "./StatusCards";
import { fetchDeviceMetrics } from "../services/api";
import { CommandSection } from "./CommandSection";
import { fetchDeviceGases } from "../services/api";
import DropdownButton from "./DropdownButton";

export function DeviceStatusPanel({
  device,
  socket,
  activeDeviceId,
  sessionActive,
  onError,
  metrics,
  cachedGasOptions,
  selectedGas,
  onSelectGas,
  onGasOptionsLoaded,
  gasSelectionError,
  onMetricsUpdate,
  onDataUpdate,
}) {
  const [gasOptions, setGasOptions] = useState(
    Array.isArray(cachedGasOptions) ? cachedGasOptions : [],
  );
  const lastFetchedDeviceKeyRef = useRef(null);

  useEffect(() => {
    if (Array.isArray(cachedGasOptions)) {
      setGasOptions(cachedGasOptions);
    }
  }, [cachedGasOptions]);

  useEffect(() => {
    async function fetchGases() {
      const deviceLookup = device?.id || device?.name;
      const deviceKey = [device?.id || "", device?.serial || "", device?.address || ""]
        .filter(Boolean)
        .join(":");

      if (!deviceLookup) {
        setGasOptions([]);
        if (onGasOptionsLoaded) onGasOptionsLoaded([]);
        lastFetchedDeviceKeyRef.current = null;
        return;
      }

      if (deviceKey && deviceKey === lastFetchedDeviceKeyRef.current) {
        return;
      }

      if (Array.isArray(cachedGasOptions) && cachedGasOptions.length > 0 && deviceKey) {
        lastFetchedDeviceKeyRef.current = deviceKey;
        return;
      }

      try {
        const result = await fetchDeviceGases(deviceLookup);
        const gases = result?.gases || [];
        const options = gases.map((g) => ({ label: g, value: g }));
        setGasOptions(options);
        if (onGasOptionsLoaded) onGasOptionsLoaded(options);
        lastFetchedDeviceKeyRef.current = deviceKey || deviceLookup;
        console.log(`[App] Fetched gases for ${device?.name}:`, options);
      } catch (err) {
        console.error("Error fetching gases:", err);
        setGasOptions([]);
        if (onGasOptionsLoaded) onGasOptionsLoaded([]);
      }
    }
    fetchGases();
  }, [device?.id, device?.serial, device?.address, device?.name, cachedGasOptions]);

   

  return (
    <div className="w-full max-w-4xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-lg p-6 mb-8 flex flex-col gap-6 transition-shadow">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b pb-3 mb-2">
        <div className="flex items-center gap-3">
          <div className="flex flex-col gap-1">
            <span className="inline-block px-3 py-1 bg-blue-100 text-blue-700 rounded font-mono text-base tracking-tight">
              {device?.calibrationFound === false ? "MFC-XXXXX" : device?.name || "Unknown"}
            </span>
            <span className="text-xs text-slate-500 font-mono">
              Serial: {device?.serial || "Unknown"}
            </span>
          </div>
          <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500 font-normal">
            {device?.type || "Device"}
          </span>
        </div>
      </div>

      {device?.calibrationFound === false && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          No calibration found for {device?.serial || device?.name || "this device"}. Using fallback calibration with slope 1.
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-6">
        <div className="flex-1 min-w-0">
          <StatusCards
            metrics={metrics}
            socket={socket}
            activeDeviceId={activeDeviceId}
            sessionActive={sessionActive}
            gasOptions={gasOptions}
            selectedGas={selectedGas}
            onSelectGas={onSelectGas}
            gasSelectionError={gasSelectionError}
            onMetricsUpdate={onMetricsUpdate}
            onDataUpdate={onDataUpdate}
          />
        </div>
        <div className="md:w-80 w-full">
          <div className="bg-gray-50 rounded-xl shadow-inner p-4 border border-gray-200 h-full flex flex-col">
            <CommandSection
              activeDeviceId={activeDeviceId}
              onError={onError}
              sessionActive={sessionActive}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

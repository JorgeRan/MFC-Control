import React, { useState } from "react";
import { CircleGauge, Download, Radio } from "lucide-react";
import { sendCommand, setSetpoint } from "../services/api";

export function CommandSection({
  activeDeviceId,
  onError = null,
  sessionActive,
}) {
  const [setpointValue, setSetpointValue] = useState("");
  const [loading, setLoading] = useState(false);

  const handleCommand = async (command) => {
    try {
      setLoading(true);
      await sendCommand(activeDeviceId, command);
      console.log(`Command "${command}" sent successfully`);
    } catch (error) {
      console.error("Error sending command:", error);
      if (onError) onError(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSetpoint = async (command) => {
    const isOffCommand = command === "OFF";
    const valueToSend = isOffCommand ? 0 : setpointValue;

    if (!isOffCommand && (!setpointValue || isNaN(setpointValue))) {
      console.warn("Please enter a valid setpoint value");
      return;
    }

    try {
      setLoading(true);
      console.log(
        `[CommandSection] Sending setpoint to device: ${activeDeviceId}, value: ${valueToSend}`,
      );
      await setSetpoint(activeDeviceId, valueToSend);
      console.log(`Setpoint set to ${valueToSend}`);
      setSetpointValue("");
    } catch (error) {
      console.error("Error setting setpoint:", error);
      if (onError) onError(error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm p-6 h-auto">
      <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center">
        <Radio className="w-5 h-5 mr-2 text-slate-400" />
        Device Commands
      </h3>

      <div className="flex flex-wrap justify-between gap-6 mb-4">
        <div className="relative w-64">
          <input
            type="number"
            placeholder="Setpoint"
            value={setpointValue}
            onChange={(e) => setSetpointValue(e.target.value)}
            className="w-full px-4 pr-16 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm">
            ln/min
          </span>
        </div>
        <div className={"flex sm:flex-row flex-col items-start gap-4"}>
          <button
            onClick={() => handleSetpoint("")}
            disabled={loading || !sessionActive}
            className={`
            inline-flex items-center px-4 py-2 
            ${sessionActive && activeDeviceId == "dev_01" ? "bg-blue-500 hover:bg-blue-600" : sessionActive && activeDeviceId == "dev_02" ? "bg-emerald-500 hover:bg-emerald-600" : ""} text-white text-sm font-medium rounded-full
            transition-colors shadow-sm
            hover:shadow

            disabled:bg-orange-300
            disabled:hover:bg-orange-300
            disabled:hover:shadow-none
            disabled:cursor-not-allowed

            focus:outline-none 
            focus:ring-2 focus:ring-offset-2 focus:ring-blue-500
          `}
          >
            <CircleGauge className="w-5 h-5 mr-2" />
            {loading ? "Sending..." : "Write Setpoint"}
          </button> <button
            onClick={() => handleSetpoint("OFF")}
            disabled={loading || !sessionActive}
            className={`
            inline-flex items-center px-4 py-2 
            ${sessionActive && activeDeviceId == "dev_01" ? "bg-red-500 hover:bg-red-600" : sessionActive && activeDeviceId == "dev_02" ? "bg-red-500 hover:bg-red-600" : ""} text-white text-sm font-medium rounded-full
            transition-colors shadow-sm
            hover:shadow

            disabled:bg-orange-300
            disabled:hover:bg-orange-300
            disabled:hover:shadow-none
            disabled:cursor-not-allowed

            focus:outline-none 
            focus:ring-2 focus:ring-offset-2 focus:ring-blue-500
          `}
          >
            
            {loading ? "Sending..." : "OFF"}
          </button>
        </div>
      </div>

      {/* <div className="flex flex-wrap gap-2">
        <button
          onClick={() => handleCommand("on")}
          disabled={loading}
          className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:bg-emerald-300 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Turn ON
        </button>
        <button
          onClick={() => handleCommand("off")}
          disabled={loading}
          className="px-4 py-2 bg-red-500 hover:bg-red-600 disabled:bg-red-300 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Turn OFF
        </button>
        <button
          onClick={() => handleCommand("toggle")}
          disabled={loading}
          className="px-4 py-2 bg-slate-500 hover:bg-slate-600 disabled:bg-slate-300 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Toggle
        </button>
      </div> */}
    </div>
  );
}

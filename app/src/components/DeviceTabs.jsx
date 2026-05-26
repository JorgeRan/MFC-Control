import React from 'react'
import { Wifi, Radio, Activity } from 'lucide-react'
export function DeviceTabs({ nodes, activeNodeId, onSelectNode, activeDeviceId, onSelectDevice }) {
  return (
    <div className="w-full border-b border-slate-200 bg-white">
      <div className="w-full px-6 flex items-center h-20">
        <div className="flex-1 min-w-0 flex space-x-8 overflow-x-auto no-scrollbar">
          {nodes.map((node) => {
            const isActive = node.id === activeNodeId;
            return (
              <button
                key={node.id}
                onClick={() => onSelectNode(node.id)}
                className={`
                  group flex items-center py-4 border-b-2 text-sm font-medium transition-all whitespace-nowrap bg-white my-3
                  ${isActive ? 'border-blue-500 text-blue-600' : 'border-slate-200 text-slate-500 hover:text-slate-700 hover:border-slate-300'}
                `}
              >
                <div
                  className={`
                  w-2 h-2 rounded-full mr-2.5 transition-colors
                  ${node.status === 'online' ? 'bg-emerald-500' : ''}
                  ${node.status === 'offline' ? 'bg-slate-300' : ''}
                  ${node.status === 'warning' ? 'bg-amber-500' : ''}
                `}
                />
                {node.name}
                <span
                  className={`
                  ml-2 text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-normal
                  ${isActive ? 'bg-blue-50 text-blue-600' : ''}
                `}
                >
                  {node.type}
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex shrink-0 ml-4 justify-end">
          <img src="/src/assets/EERL_Logo.png" alt="EERL Logo" className="my-4 w-20 h-auto" />
        </div>
      </div>
    </div>
  );
}

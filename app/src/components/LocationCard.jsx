import React from 'react'
import { MapPin, ExternalLink, Navigation } from 'lucide-react'
export function LocationCard({ lat, lng, address }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-slate-900 flex items-center">
          <MapPin className="w-5 h-5 mr-2 text-slate-400" />
          Location
        </h3>
        <a
          href={`https://www.google.com/maps/search/?api=1&query=${lat},${lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-blue-600 hover:text-blue-700 font-medium flex items-center"
        >
          View on Map
          <ExternalLink className="w-3 h-3 ml-1" />
        </a>
      </div>

      <div className="bg-slate-50 rounded-lg p-4 mb-4 border border-slate-100">
        <div className="flex items-start">
          <Navigation className="w-5 h-5 text-blue-500 mt-0.5 mr-3 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-slate-900 mb-1">{address}</p>
            <p className="text-xs text-slate-500 font-mono">
              {lat.toFixed(6)}, {lng.toFixed(6)}
            </p>
          </div>
        </div>
      </div>

      <div className="relative w-full h-32 bg-slate-100 rounded-lg overflow-hidden border border-slate-200">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-200 via-slate-100 to-slate-300 opacity-70" />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-3 h-3 bg-blue-500 rounded-full ring-4 ring-blue-500/20 animate-pulse" />
        </div>
        <div className="absolute bottom-2 right-2 text-[10px] text-slate-400 bg-white/80 px-1 rounded">
          Map Data © OpenStreetMap
        </div>
      </div>
    </div>
  )
}

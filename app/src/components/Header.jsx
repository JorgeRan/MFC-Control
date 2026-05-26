// import React from 'react'
// import { Search, Bell, Settings, ChevronRight, Home } from 'lucide-react'
// export function Header({ deviceName }) {
//   return (
//     <header className="w-full border-b border-slate-200 bg-white px-6 py-4">
//       <div className="flex items-center justify-between max-w-7xl mx-auto">
//         {/* Breadcrumbs */}
//         <nav className="flex items-center text-sm text-slate-500">
//           <a
//             href="#"
//             className="flex items-center hover:text-slate-900 transition-colors"
//           >
//             <Home className="w-4 h-4 mr-1" />
//             Dashboard
//           </a>
//           <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
//           <span className="hover:text-slate-900 cursor-pointer transition-colors">
//             Devices
//           </span>
//           <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
//           <span className="font-medium text-slate-900 bg-slate-100 px-2 py-0.5 rounded-md">
//             {deviceName}
//           </span>
//         </nav>

//         {/* Right Actions */}
//         <div className="flex items-center space-x-4">
//           <div className="relative hidden md:block">
//             <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
//             <input
//               type="text"
//               placeholder="Search devices..."
//               className="pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 w-64 transition-all"
//             />
//           </div>
//           <button className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-full transition-colors relative">
//             <Bell className="w-5 h-5" />
//             <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
//           </button>
//           <button className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-full transition-colors">
//             <Settings className="w-5 h-5" />
//           </button>
//           <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-medium text-sm border border-blue-200">
//             JD
//           </div>
//         </div>
//       </div>
//     </header>
//   )
// }

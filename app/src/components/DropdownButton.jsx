import React, { useState, useRef, useEffect } from 'react'

export function DropdownButton({ selected: selectedProp, onChange, sessionActive, gasOptions, hasError = false }) {
  // const gasOptions = [
  //   { label: 'Nitrous Oxide (N2O)', value: 'n2o' },
  //   { label: 'Acetylene (C2H2)', value: 'c2h2' },
  //   { label: 'Ethene (C2H4)', value: 'c2h4' },
  //   { label: 'Methane (CH4)', value: 'ch4' },
  // ]

  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(
    selectedProp || (gasOptions && gasOptions.length > 0 ? gasOptions[0].value : undefined)
  )
  const rootRef = useRef(null)

  useEffect(() => {
    if (selectedProp) setSelected(selectedProp)
  }, [selectedProp])

  useEffect(() => {
    function onDoc(e) {
      if (!rootRef.current) return
      if (!rootRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDoc)
    return () => document.removeEventListener('pointerdown', onDoc)
  }, [])

  const handleSelect = (value) => {
    setSelected(value)
    setOpen(false)
    if (onChange) onChange(value)
  }

  const currentLabel = gasOptions.find((g) => g.value === selected)?.label || 'Gas'

  if (gasOptions.length === 0) {
    hasError = false; // Don't show error state if there are simply no options
  }

  return (
    <div className="relative inline-block" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`px-3 py-1 rounded text-sm font-medium border ${
          hasError
            ? 'bg-red-50 border-red-500 text-red-700 hover:bg-red-100'
            : 'bg-slate-100 border-slate-200 hover:bg-slate-200'
        }`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-invalid={hasError}
        disabled={sessionActive}
      >
        {currentLabel}
        <span className="ml-2">▾</span>
        
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute right-0 mt-2 w-48 bg-white border border-slate-200 rounded shadow-md z-50"
        >
          {gasOptions.map((g) => (
            <li
              key={g.value}
              role="option"
              aria-selected={g.value === selected}
              onClick={() => handleSelect(g.value)}
              className={`px-3 py-2 text-sm hover:bg-slate-100 cursor-pointer ${g.value === selected ? 'bg-slate-100 font-semibold' : ''}`}
            >
              {g.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default DropdownButton
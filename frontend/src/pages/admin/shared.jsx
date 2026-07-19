import { X, MagnifyingGlass } from "@phosphor-icons/react";

export function Modal({ children, onClose, title }) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white brutal-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="border-b-2 border-black p-4 flex items-center justify-between sticky top-0 bg-[#FFD60A]">
          <div className="font-display font-black text-xl">{title}</div>
          <button onClick={onClose} data-testid="modal-close"><X weight="bold" size={24} /></button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

export function F({ label, children }) {
  return (
    <label className="block">
      <div className="font-mono text-xs uppercase mb-2">{label}</div>
      {children}
    </label>
  );
}

export function SearchInput({ value, onChange, placeholder, testid }) {
  return (
    <div className="brutal-sm bg-white flex items-center gap-2 px-3 py-2">
      <MagnifyingGlass weight="bold" size={16} />
      <input
        data-testid={testid}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="border-none outline-none w-56 text-sm bg-transparent"
      />
      {value && (
        <button onClick={() => onChange("")} className="text-gray-500 hover:text-black" title="Clear">
          <X weight="bold" size={14} />
        </button>
      )}
    </div>
  );
}

export function Note({ title, body }) {
  return (
    <div className="brutal-sm bg-[#FFD60A]/40 p-5">
      <div className="font-display font-bold">{title}</div>
      <p className="text-sm text-gray-800 mt-1">{body}</p>
    </div>
  );
}

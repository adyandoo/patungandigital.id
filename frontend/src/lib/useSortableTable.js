import { useMemo, useState } from "react";
import { CaretUp, CaretDown, CaretUpDown } from "@phosphor-icons/react";

/**
 * Hook to sort an array by a column key with ASC/DESC toggle.
 * Returns:
 *   - sorted: the sorted array
 *   - sortKey, sortDir
 *   - handleSort(key): toggles the sort
 *   - HeaderButton: <HeaderButton k="name" label="Nama" />
 */
export function useSortableTable(rows, defaultKey = null, defaultDir = "asc", accessors = {}) {
  const [sortKey, setSortKey] = useState(defaultKey);
  const [sortDir, setSortDir] = useState(defaultDir);

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("asc"); }
  };

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const get = accessors[sortKey] || ((r) => r[sortKey]);
    const dir = sortDir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = get(a), vb = get(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
      return String(va).localeCompare(String(vb), "id") * dir;
    });
  }, [rows, sortKey, sortDir, accessors]);

  const HeaderButton = ({ k, label, testId }) => (
    <button
      type="button"
      onClick={() => handleSort(k)}
      data-testid={testId || `sort-${k}`}
      className="inline-flex items-center gap-1 font-mono text-xs uppercase text-gray-600 hover:text-black"
    >
      <span>{label}</span>
      {sortKey === k ? (sortDir === "asc" ? <CaretUp size={12} weight="bold" /> : <CaretDown size={12} weight="bold" />) : <CaretUpDown size={12} />}
    </button>
  );

  return { sorted, sortKey, sortDir, handleSort, HeaderButton };
}

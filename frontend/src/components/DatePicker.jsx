import { useState } from "react";
import { format } from "date-fns";
import { id as idLocale } from "date-fns/locale";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Calendar as CalendarIcon, X } from "@phosphor-icons/react";

/** DatePicker — Shadcn Calendar with Indonesian locale.
 *  Props:
 *   - value: ISO date string (yyyy-MM-dd) or empty
 *   - onChange: (isoDateString: string) => void
 *   - testId, placeholder, minDate, allowClear
 */
export default function DatePicker({ value, onChange, testId, placeholder = "Pilih tanggal", minDate, allowClear = true }) {
  const [open, setOpen] = useState(false);
  const dateObj = value ? new Date(value + (value.length === 10 ? "T00:00:00" : "")) : null;
  const label = dateObj ? format(dateObj, "d MMMM yyyy", { locale: idLocale }) : placeholder;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid={testId}
          className={`brutal-input flex items-center justify-between w-full text-left ${!dateObj ? "text-gray-500" : ""}`}
        >
          <span className="flex items-center gap-2">
            <CalendarIcon weight="duotone" size={18} /> {label}
          </span>
          {value && allowClear && (
            <span
              role="button"
              aria-label="Hapus tanggal"
              onClick={(e) => { e.stopPropagation(); onChange(""); }}
              className="p-0.5 rounded hover:bg-black/10 cursor-pointer"
              data-testid={`${testId}-clear`}
            >
              <X size={14} />
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="p-0 border-2 border-black bg-white">
        <Calendar
          mode="single"
          selected={dateObj}
          onSelect={(d) => {
            if (d) {
              const iso = format(d, "yyyy-MM-dd");
              onChange(iso);
              setOpen(false);
            }
          }}
          locale={idLocale}
          fromDate={minDate}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
}

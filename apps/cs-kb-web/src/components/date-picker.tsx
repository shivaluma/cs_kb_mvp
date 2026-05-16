import { useMemo, useState } from "react";
import { IconCalendar as CalendarIcon } from "@tabler/icons-react";

import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { formatIsoDate, parseIsoDate } from "@/lib/date";
import { cn } from "@/lib/utils";

export function DatePicker({
  disabled = false,
  label,
  onChange,
  placeholder = "Pick date",
  value,
}: {
  disabled?: boolean;
  label?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  const [open, setOpen] = useState(false);
  const selectedDate = useMemo(() => parseIsoDate(value), [value]);
  const accessibleLabel = label ? `${label}: ${value || placeholder}` : value ? `Selected date ${value}` : placeholder;

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger asChild>
        <Button
          aria-label={accessibleLabel}
          className={cn("w-full justify-start rounded-md px-3 text-left font-normal", !value && "text-muted-foreground")}
          disabled={disabled}
          type="button"
          variant="outline"
        >
          <CalendarIcon data-icon="inline-start" className="size-4" />
          <span>{value || placeholder}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="p-0">
        <Calendar
          defaultMonth={selectedDate ?? new Date()}
          mode="single"
          onSelect={(date) => {
            if (!date) {
              return;
            }
            onChange(formatIsoDate(date));
            setOpen(false);
          }}
          selected={selectedDate}
        />
      </PopoverContent>
    </Popover>
  );
}

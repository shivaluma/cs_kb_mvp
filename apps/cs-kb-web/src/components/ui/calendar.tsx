"use client";

import {
  IconChevronLeft as ChevronLeft,
  IconChevronRight as ChevronRight,
  IconChevronDown as ChevronDown,
} from "@tabler/icons-react";
import { DayPicker } from "react-day-picker";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: React.ComponentProps<typeof DayPicker>) {
  return (
    <DayPicker
      className={cn("p-3", className)}
      classNames={{
        root: cn("w-fit", classNames?.root),
        months: cn("flex flex-col gap-4 sm:flex-row", classNames?.months),
        month: cn("space-y-4", classNames?.month),
        month_caption: cn("flex h-8 items-center justify-center px-8", classNames?.month_caption),
        caption_label: cn("text-sm font-medium", classNames?.caption_label),
        nav: cn("absolute inset-x-3 top-3 flex items-center justify-between", classNames?.nav),
        button_previous: cn(buttonVariants({ variant: "ghost", size: "icon-sm" }), "size-8 opacity-70 hover:opacity-100", classNames?.button_previous),
        button_next: cn(buttonVariants({ variant: "ghost", size: "icon-sm" }), "size-8 opacity-70 hover:opacity-100", classNames?.button_next),
        month_grid: cn("w-full border-collapse", classNames?.month_grid),
        weekdays: cn("flex", classNames?.weekdays),
        weekday: cn("w-9 rounded-md text-[0.8rem] font-normal text-muted-foreground", classNames?.weekday),
        week: cn("mt-1 flex w-full", classNames?.week),
        day: cn("relative size-9 p-0 text-center text-sm", classNames?.day),
        day_button: cn(
          buttonVariants({ variant: "ghost" }),
          "size-9 rounded-md p-0 font-normal aria-selected:opacity-100",
          classNames?.day_button,
        ),
        today: cn("[&>button]:border [&>button]:border-primary/50", classNames?.today),
        outside: cn("text-muted-foreground opacity-45", classNames?.outside),
        disabled: cn("text-muted-foreground opacity-35", classNames?.disabled),
        selected: cn("[&>button]:bg-primary [&>button]:text-primary-foreground [&>button]:hover:bg-primary [&>button]:hover:text-primary-foreground", classNames?.selected),
        ...classNames,
      }}
      components={{
        Chevron: ({ className: chevronClassName, orientation }) => {
          if (orientation === "left") {
            return <ChevronLeft className={cn("size-4", chevronClassName)} />;
          }
          if (orientation === "right") {
            return <ChevronRight className={cn("size-4", chevronClassName)} />;
          }
          return <ChevronDown className={cn("size-4", chevronClassName)} />;
        },
      }}
      showOutsideDays={showOutsideDays}
      {...props}
    />
  );
}

export { Calendar };

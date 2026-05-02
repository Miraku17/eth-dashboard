/**
 * shadcn/ui Select — wraps Radix UI Select primitives with the project's
 * Tailwind tokens. Source: https://ui.shadcn.com/docs/components/select
 *
 * Components exported (composable, lower-case import below for the simple
 * single-value dropdown the panels use):
 *   <Select>           — root, takes value/onValueChange
 *   <SelectTrigger>    — the visible button
 *   <SelectValue>      — placeholder + selected-value renderer
 *   <SelectContent>    — popover container
 *   <SelectItem>       — one option row
 *   <SimpleSelect>     — convenience wrapper that takes the same
 *                        (value, onChange, options) shape we use elsewhere
 */
import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "../../lib/cn";

const Select = SelectPrimitive.Root;
const SelectGroup = SelectPrimitive.Group;
const SelectValue = SelectPrimitive.Value;

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center justify-between gap-1 rounded-md border border-surface-border bg-surface-sunken px-2.5 py-1 text-xs font-medium tracking-wide text-white",
      "hover:bg-surface-raised focus:outline-none focus-visible:ring-1 focus-visible:ring-slate-400",
      "data-[placeholder]:text-slate-400 [&>span]:line-clamp-1",
      "disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-3 w-3 opacity-60" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      position={position}
      sideOffset={4}
      className={cn(
        "relative z-50 max-h-[--radix-select-content-available-height] min-w-[8rem] overflow-hidden rounded-md border border-surface-border bg-surface-card text-slate-200 shadow-lg",
        "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
        "data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2",
        position === "popper" &&
          "data-[side=bottom]:translate-y-1 data-[side=top]:-translate-y-1",
        className,
      )}
      {...props}
    >
      <SelectPrimitive.Viewport
        className={cn(
          "p-1",
          position === "popper" &&
            "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]",
        )}
      >
        {children}
      </SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex w-full cursor-pointer select-none items-center rounded-sm py-1 pl-6 pr-2 text-xs outline-none",
      "focus:bg-surface-raised focus:text-white",
      "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className,
    )}
    {...props}
  >
    <span className="absolute left-1.5 flex h-3 w-3 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-3 w-3" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;

/**
 * Convenience wrapper preserving the simple {value, onChange, options}
 * API the existing panels use. Internally composes the shadcn primitives.
 */
type Option<T> = { value: T; label: React.ReactNode };

type SimpleSelectProps<T extends string | number> = {
  value: T;
  onChange: (v: T) => void;
  options: readonly Option<T>[] | readonly T[];
  size?: "sm" | "xs"; // accepted for API compat with Pill; visual is fixed
  ariaLabel?: string;
  className?: string;
};

function SimpleSelect<T extends string | number>({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}: SimpleSelectProps<T>) {
  const items: Option<T>[] = (options as readonly (Option<T> | T)[]).map((o) =>
    typeof o === "object" && o !== null && "value" in o
      ? (o as Option<T>)
      : ({ value: o as T, label: String(o) }),
  );
  const valueAsString = String(value);

  return (
    <Select
      value={valueAsString}
      onValueChange={(raw) => {
        const matched = items.find((i) => String(i.value) === raw);
        if (matched) onChange(matched.value);
      }}
    >
      <SelectTrigger aria-label={ariaLabel} className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((it) => (
          <SelectItem key={String(it.value)} value={String(it.value)}>
            {it.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectItem,
  SimpleSelect,
};
export default SimpleSelect;

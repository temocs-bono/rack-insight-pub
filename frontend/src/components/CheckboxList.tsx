export interface CheckboxOption {
  value: string;
  label: string;
  hint?: string;
}

interface CheckboxListProps {
  options: CheckboxOption[];
  selected: string[];
  onToggle: (value: string) => void;
  emptyText?: string;
  maxHeightClass?: string;
}

/** Compact, scrollable multi-select used for group members, role assignment,
 *  and user group membership. */
export function CheckboxList({
  options,
  selected,
  onToggle,
  emptyText = "Nothing to show.",
  maxHeightClass = "max-h-64",
}: CheckboxListProps) {
  return (
    <div
      className={`flex ${maxHeightClass} flex-col gap-1 overflow-y-auto rounded-md border border-gray-200 p-2`}
    >
      {options.length === 0 ? (
        <span className="text-sm text-gray-400">{emptyText}</span>
      ) : (
        options.map((opt) => (
          <label key={opt.value} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(opt.value)}
              onChange={() => onToggle(opt.value)}
            />
            <span>{opt.label}</span>
            {opt.hint && <span className="text-xs text-gray-400">{opt.hint}</span>}
          </label>
        ))
      )}
    </div>
  );
}

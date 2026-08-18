import { useMemo } from "react";
import type { Permission } from "@/types";

interface PermissionPickerProps {
  permissions: Permission[];
  selected: string[];
  onToggle: (code: string) => void;
}

/** Permission checkboxes grouped by category. Used by the Role editor;
 *  permissions are system-managed and never edited directly. */
export function PermissionPicker({ permissions, selected, onToggle }: PermissionPickerProps) {
  const byCategory = useMemo(() => {
    const map = new Map<string, Permission[]>();
    for (const perm of permissions) {
      const list = map.get(perm.category) ?? [];
      list.push(perm);
      map.set(perm.category, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [permissions]);

  return (
    <div className="flex max-h-80 flex-col gap-3 overflow-y-auto rounded-md border border-gray-200 p-3">
      {byCategory.map(([category, perms]) => (
        <div key={category} className="flex flex-col gap-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            {category}
          </p>
          {perms.map((perm) => (
            <label key={perm.code} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(perm.code)}
                onChange={() => onToggle(perm.code)}
              />
              <code className="text-xs text-gray-600">{perm.code}</code>
              <span className="text-gray-500">— {perm.name}</span>
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

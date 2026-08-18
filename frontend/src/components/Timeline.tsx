import type { ReactNode } from "react";

export interface TimelineItem {
  id: string;
  icon: ReactNode;
  content: ReactNode;
  timestamp: string;
}

/** Vertical timeline used by Device History and the History page. */
export function Timeline({ items }: { items: TimelineItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-gray-400">Nothing recorded yet.</p>;
  }
  return (
    <ol className="relative flex flex-col gap-4 border-l border-gray-200 pl-6">
      {items.map((item) => (
        <li key={item.id} className="relative">
          <span className="absolute -left-[31px] flex h-5 w-5 items-center justify-center rounded-full border border-gray-200 bg-white">
            {item.icon}
          </span>
          <p className="mb-1 text-xs text-gray-400">
            {new Date(item.timestamp).toLocaleString()}
          </p>
          {item.content}
        </li>
      ))}
    </ol>
  );
}

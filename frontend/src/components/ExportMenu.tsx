import { Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import { toast } from "@/stores/toast";

const FORMATS = [
  { id: "xlsx", label: "Excel (.xlsx)" },
  { id: "csv", label: "CSV (.zip)" },
  { id: "json", label: "JSON" },
] as const;

interface ExportMenuProps {
  scope: "device" | "rack" | "cluster" | "all";
  targetId?: string;
  label?: string;
}

export function ExportMenu({ scope, targetId, label = "Export" }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const download = async (format: (typeof FORMATS)[number]["id"]) => {
    setOpen(false);
    setBusy(true);
    try {
      await api.downloadExport(scope, format, targetId);
      toast.success("Export ready", "Download started");
    } catch {
      toast.error("Export failed", "Could not generate the export file");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <Button variant="outline" size="sm" onClick={() => setOpen(!open)} disabled={busy}>
        <Download className="h-4 w-4" />
        {busy ? "Exporting…" : label}
      </Button>
      {open && (
        <div className="absolute right-0 z-30 mt-1 w-44 rounded-md border border-gray-200 bg-white py-1 shadow-lg">
          {FORMATS.map((format) => (
            <button
              key={format.id}
              type="button"
              className="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100"
              onClick={() => download(format.id)}
            >
              {format.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

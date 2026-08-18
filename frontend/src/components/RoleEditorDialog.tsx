import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { PermissionPicker } from "@/components/PermissionPicker";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { usePermissions } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { Role } from "@/types";

interface RoleEditorDialogProps {
  open: boolean;
  /** null → create a new role; a role → edit it. */
  role: Role | null;
  onClose: () => void;
  onSaved?: (roleId: string) => void;
}

export function RoleEditorDialog({ open, role, onClose, onSaved }: RoleEditorDialogProps) {
  const { data: permissions } = usePermissions();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [codes, setCodes] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    setName(role?.name ?? "");
    setDescription(role?.description ?? "");
    setCodes(role?.permission_codes ?? []);
  }, [open, role]);

  const toggle = (code: string) =>
    setCodes((c) => (c.includes(code) ? c.filter((x) => x !== code) : [...c, code]));

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name,
        description: description || null,
        permission_codes: codes,
      };
      return role ? api.updateRole(role.id, payload) : api.createRole(payload);
    },
    onSuccess: (saved) => {
      toast.success(role ? "Role updated" : "Role created", name);
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
      if (role) void queryClient.invalidateQueries({ queryKey: ["role", role.id] });
      onClose();
      onSaved?.(saved.id);
    },
    onError: (err) =>
      toast.error("Save failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={role ? `Edit Role — ${role.name}` : "Create Role"}
      className="max-w-2xl"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending || !name}>
            {save.isPending ? "Saving…" : role ? "Save Changes" : "Create"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="Name *">
          <Input value={name} autoFocus onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Description">
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label={`Permissions (${codes.length} selected)`}>
          <PermissionPicker
            permissions={permissions ?? []}
            selected={codes}
            onToggle={toggle}
          />
        </Field>
      </div>
    </Dialog>
  );
}

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DEMO, updateSessionTitle } from "../lib/api";

export function EditableSessionTitle({
  sessionId,
  title,
  className = "font-display font-bold",
}: {
  sessionId: string;
  title: string | null | undefined;
  className?: string;
}) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title || "");

  useEffect(() => {
    setDraft(title || "");
  }, [title]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const mutation = useMutation({
    mutationFn: (nextTitle: string) => updateSessionTitle(sessionId, nextTitle),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      setEditing(false);
    },
    onError: () => {
      setEditing(true);
    },
  });

  const save = () => {
    const next = draft.trim();
    if (!next) {
      setDraft(title || "");
      setEditing(false);
      return;
    }
    if (next === (title || "").trim()) {
      setEditing(false);
      return;
    }
    mutation.mutate(next);
  };

  if (DEMO) return <span className={className}>{title || "Untitled session"}</span>;

  if (editing) {
    return (
      <div className="w-full min-w-0">
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") {
              setDraft(title || "");
              setEditing(false);
            }
          }}
          onClick={(e) => e.preventDefault()}
          disabled={mutation.isPending}
          className={`${className} w-full min-w-0 border-2 border-ink bg-card px-2 py-1`}
          aria-label="Session name"
        />
        {mutation.isError && (
          <p className="mt-1 text-xs text-cozy-red">
            Rename failed — restart the backend (<code>uv run open-paxel serve</code>) and try again.
          </p>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setEditing(true);
      }}
      className={`${className} text-left hover:underline`}
      title="Click to rename"
    >
      {title || "Untitled session"}
    </button>
  );
}

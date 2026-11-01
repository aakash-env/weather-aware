import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { geocode } from "../api/client";
import type { PlaceInput } from "../types";

interface PlaceFieldProps {
  label: string;
  value: PlaceInput | null;
  onChange: (place: PlaceInput | null) => void;
}

export function PlaceField({ label, value, onChange }: PlaceFieldProps) {
  const inputId = useId();
  const listId = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(text.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [text]);

  const query = useQuery({
    queryKey: ["geocode", debounced],
    queryFn: () => geocode(debounced),
    enabled: debounced.length >= 2 && text !== value?.label,
    staleTime: 60_000,
  });

  const hits = query.data ?? [];

  return (
    <div className="field">
      <label htmlFor={inputId}>{label}</label>
      <input
        id={inputId}
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        value={text}
        placeholder="City or address"
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && hits.length > 0 && (
        <ul id={listId} role="listbox" className="suggestions">
          {hits.map((hit) => (
            <li key={`${hit.label}-${hit.lat}-${hit.lon}`}>
              <button
                type="button"
                role="option"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onChange(hit);
                  setText(hit.label);
                  setOpen(false);
                }}
              >
                {hit.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {query.isError && <p className="hint error">{(query.error as Error).message}</p>}
    </div>
  );
}

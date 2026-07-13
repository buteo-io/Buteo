import { useState, useRef, useEffect } from "react";

type Option = {
  value: string;
  label: string;
};

type Props = {
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  style?: React.CSSProperties;
};

export function Select({ value, onChange, options, style }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedOption = options.find((o) => o.value === value) || options[0];

  return (
    <div className="custom-select" ref={containerRef} style={style}>
      <button
        type="button"
        className="custom-select-trigger"
        onClick={() => setOpen(!open)}
      >
        <span>{selectedOption?.label}</span>
        <span className="custom-select-arrow">▼</span>
      </button>
      {open && (
        <ul className="custom-select-options">
          {options.map((o) => (
            <li
              key={o.value}
              className={`custom-select-option ${o.value === value ? "active" : ""}`}
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

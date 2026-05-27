type Props = {
  type: string | null;
  size?: number;
  className?: string;
};

export function PlaceTypeIcon({ type, size = 16, className }: Props) {
  const props = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    className,
  };

  switch (type) {
    case "POI":
      return (
        <svg {...props} fill="currentColor" stroke="none">
          <path d="M12 2C8.134 2 5 5.134 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.866-3.134-7-7-7zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z" />
        </svg>
      );
    case "Drinking Water":
      return (
        <svg {...props}>
          <path d="M12 2a5 5 0 0 1 5 5c0 4-5 10-5 10S7 11 7 7a5 5 0 0 1 5-5z" />
          <path d="M6 17a4 4 0 0 0 4 4M18 17a4 4 0 0 1-4 4" strokeDasharray="2 1" />
          <line x1="12" y1="21" x2="12" y2="23" />
        </svg>
      );
    case "Camping":
      return (
        <svg {...props}>
          <path d="M3 21l9-16 9 16H3z" />
          <path d="M12 5v0" />
          <line x1="7.5" y1="21" x2="12" y2="13" />
          <line x1="16.5" y1="21" x2="12" y2="13" />
        </svg>
      );
    case "Parking":
      return (
        <svg {...props}>
          <rect x="3" y="3" width="18" height="18" rx="3" />
          <path d="M9 17V7h5a3 3 0 0 1 0 6H9" />
        </svg>
      );
    default:
      return (
        <svg {...props} fill="currentColor" stroke="none">
          <circle cx="12" cy="12" r="4" />
        </svg>
      );
  }
}

// Small reusable row of edit/delete icon buttons.
// Used by the Places and Trips lists where the same UI appeared twice.

type Props = {
  onEdit: () => void;
  onDelete: () => void;
  confirmDelete?: string;
};

export function EditDeleteActions({ onEdit, onDelete, confirmDelete }: Props) {
  return (
    <div className="actions">
      <button
        className="icon-btn"
        onClick={(e) => {
          e.stopPropagation();
          onEdit();
        }}
        title="Edit"
        aria-label="Edit"
      >
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
        </svg>
      </button>
      <button
        className="icon-btn icon-btn-danger"
        onClick={(e) => {
          e.stopPropagation();
          if (!confirmDelete || confirm(confirmDelete)) onDelete();
        }}
        title="Delete"
        aria-label="Delete"
      >
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 6h18" />
          <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
        </svg>
      </button>
    </div>
  );
}

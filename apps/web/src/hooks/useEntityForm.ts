import { useState, useEffect, useRef } from "react";
import { MediaItem } from "../api";

export type UseEntityFormOptions<M> = {
  initialName: string;
  initialNotes: string;
  entityId?: string;
  fetchMedia?: (id: string) => Promise<M[]>;
  uploadMedia?: (id: string, file: File) => Promise<M>;
  deleteMedia?: (id: string, mediaId: string) => Promise<void>;
  onSubmit: (data: { name: string; notes: string }) => Promise<void>;
  onMediaChange?: (media: M[]) => void;
};

export function useEntityForm<M extends MediaItem>({
  initialName,
  initialNotes,
  entityId,
  fetchMedia,
  uploadMedia,
  deleteMedia,
  onSubmit,
  onMediaChange,
}: UseEntityFormOptions<M>) {
  const [name, setName] = useState(initialName);
  const [notes, setNotes] = useState(initialNotes);
  const [media, setMedia] = useState<M[]>([]);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const onMediaChangeRef = useRef(onMediaChange);
  useEffect(() => {
    onMediaChangeRef.current = onMediaChange;
  });

  useEffect(() => {
    setName(initialName);
    setNotes(initialNotes);
    setMedia([]);
    setError(null);

    if (entityId && fetchMedia) {
      fetchMedia(entityId)
        .then((fetched) => {
          setMedia(fetched);
          onMediaChangeRef.current?.(fetched);
        })
        .catch(() => {});
    }
  }, [entityId, initialName, initialNotes, fetchMedia]);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), notes: notes.trim() });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !entityId || !uploadMedia) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadMedia(entityId, file);
      setMedia((cur) => {
        const next = [uploaded, ...cur];
        onMediaChangeRef.current?.(next);
        return next;
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to upload");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteMedia = async (mediaId: string) => {
    if (!entityId || !deleteMedia) return;
    if (!confirm("Delete this photo/video?")) return;
    setError(null);
    try {
      await deleteMedia(entityId, mediaId);
      setMedia((cur) => {
        const next = cur.filter((m) => m.id !== mediaId);
        onMediaChangeRef.current?.(next);
        return next;
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  return {
    name,
    setName,
    notes,
    setNotes,
    media,
    saving,
    uploading,
    error,
    setError,
    fileInputRef,
    handleSubmit,
    handleUpload,
    handleDeleteMedia,
  };
}
